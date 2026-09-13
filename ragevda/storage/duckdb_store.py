"""Local zero-cost vector database (DuckDB).

Stores harvested documents and their chunk embeddings on disk for **$0**
forever -- replacing paid Pinecone / Weaviate cloud vector DBs.  DuckDB's
native ``ARRAY`` type and ``array_cosine_similarity`` let us run real vector
nearest-neighbour queries locally.  If DuckDB is unavailable the store
degrades to an in-memory no-op so the rest of the pipeline still runs.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..harvester.base import Document
from ..utils import get_logger

logger = get_logger("ragevda.storage.duckdb")


class CorpusStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.available = False
        self.con = None
        try:
            import duckdb  # type: ignore

            os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
            self.con = duckdb.connect(db_path)
            self.available = True
            self._init_schema()
            logger.info("DuckDB corpus store at %s", db_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DuckDB unavailable (%s); using in-memory store", exc)
            self._mem_docs: Dict[str, Document] = {}
            self._mem_chunks: Dict[str, List[np.ndarray]] = {}
            self._mem_entity: Dict[str, np.ndarray] = {}

    # ------------------------------------------------------------------
    def _init_schema(self) -> None:
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id VARCHAR PRIMARY KEY,
                url VARCHAR,
                title VARCHAR,
                source_type VARCHAR,
                query VARCHAR,
                domain VARCHAR,
                extracted_at VARCHAR,
                text VARCHAR
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS chunk_embeddings (
                doc_id VARCHAR,
                chunk_index INTEGER,
                embedding FLOAT[],
                CONSTRAINT pk_chunk PRIMARY KEY (doc_id, chunk_index)
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS entity_centroids (
                entity VARCHAR PRIMARY KEY,
                embedding FLOAT[]
            )
        """)

    # ------------------------------------------------------------------
    def insert_document(self, doc: Document) -> None:
        if self.available:
            self.con.execute(
                "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?)",
                [doc.doc_id, doc.url, doc.title, doc.source_type,
                 doc.query, doc.domain, doc.extracted_at, doc.text[:50_000]],
            )
        else:
            self._mem_docs[doc.doc_id] = doc

    def insert_chunk_embeddings(self, doc_id: str, vectors: np.ndarray) -> None:
        if vectors is None or len(vectors) == 0:
            return
        if self.available:
            rows = [
                (doc_id, i, list(map(float, vec)))
                for i, vec in enumerate(vectors)
            ]
            self.con.executemany(
                "INSERT OR REPLACE INTO chunk_embeddings VALUES (?,?,?)", rows
            )
        else:
            self._mem_chunks[doc_id] = list(vectors)

    def insert_entity_centroid(self, entity: str, vec: np.ndarray) -> None:
        if self.available:
            self.con.execute(
                "INSERT OR REPLACE INTO entity_centroids VALUES (?,?)",
                [entity, list(map(float, vec))],
            )
        else:
            self._mem_entity[entity] = vec

    # ------------------------------------------------------------------
    def similar_to_vector(self, vec: np.ndarray, k: int = 20,
                          min_sim: float = 0.0) -> List[Tuple[str, float]]:
        q = list(map(float, vec))
        if self.available:
            try:
                rows = self.con.execute(
                    """
                    SELECT doc_id,
                           MAX(array_cosine_similarity(embedding, ?)) AS sim
                    FROM chunk_embeddings
                    GROUP BY doc_id
                    HAVING sim >= ?
                    ORDER BY sim DESC
                    LIMIT ?
                    """,
                    [q, min_sim, k],
                ).fetchall()
                return [(r[0], float(r[1])) for r in rows]
            except Exception as exc:  # noqa: BLE001
                # Older DuckDB without array_cosine_similarity: fall through
                # to the exact in-memory cosine path (real math, no fake data).
                logger.warning("DuckDB vector fn unavailable (%s); using local cosine", exc)
        # in-memory fallback
        out = []
        for doc_id, vecs in self._mem_chunks.items():
            sims = [float(np.dot(v, vec) / (np.linalg.norm(v) * np.linalg.norm(vec) or 1))
                    for v in vecs]
            out.append((doc_id, max(sims) if sims else 0.0))
        out = [(d, s) for d, s in out if s >= min_sim]
        out.sort(key=lambda x: x[1], reverse=True)
        return out[:k]

    def doc_url(self, doc_id: str) -> str:
        if self.available:
            r = self.con.execute(
                "SELECT url FROM documents WHERE doc_id=?", [doc_id]
            ).fetchone()
            return r[0] if r else ""
        return self._mem_docs.get(doc_id, Document(doc_id, "", "", "", "")).url

    def count_documents(self) -> int:
        if self.available:
            return self.con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        return len(self._mem_docs)

    def close(self) -> None:
        if self.con is not None:
            self.con.close()

    def export_parquet(self, path: str) -> None:
        if not self.available:
            return
        if "'" in path or ";" in path or "\n" in path:
            raise ValueError("refusing to export to unsafe parquet path")
        if not path.lower().endswith(".parquet"):
            raise ValueError("parquet export path must end in .parquet")
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        # Path is validated above (no quotes/semicolons); COPY cannot bind
        # a file path as a query parameter, so validated interpolation is used.
        self.con.execute(
            f"COPY (SELECT * FROM documents) TO '{path}' (FORMAT PARQUET)"
        )
