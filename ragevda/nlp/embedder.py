"""Local vector embedding & semantic mapping.

Primary engine: Hugging Face ``sentence-transformers`` running fully locally
(e.g. ``all-MiniLM-L6-v2`` or ``bge-small-en-v1.5``).  All computation stays
on the operator's machine -- no OpenAI / paid API calls.

There is NO synthetic fallback in the default path: when
``require_real=True`` (the orchestrator default) and no locally-cached real
checkpoint can be loaded, initialisation raises ``RuntimeError`` instead of
emitting degraded vectors. A hashing-vectorizer triage path exists only for
explicit opt-in (``use_fallback=True`` or ``require_real=False``) and is always
reported as ``tfidf-fallback`` in ``kind()`` and the run's ``data_integrity``.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional

import numpy as np

from ..utils import get_logger

logger = get_logger("ragevda.nlp.embedder")


class _EmbedCache:
    """SQLite embedding cache keyed by sha1(model + text).

    Avoids re-encoding identical chunks across runs/docs (big win at 5k docs).
    Location: ``~/.cache/ragevda/embed_cache.sqlite3`` or ``cache_dir``.
    Fail-open: any error disables caching for the process (never aborts audit).
    """

    def __init__(self, cache_dir: str = "") -> None:
        import os as _os
        self.enabled = False
        self._mem: dict = {}
        try:
            base = cache_dir or _os.path.join(
                _os.path.expanduser("~"), ".cache", "ragevda")
            _os.makedirs(base, exist_ok=True)
            self.path = _os.path.join(base, "embed_cache.sqlite3")
            import sqlite3
            con = sqlite3.connect(self.path)
            con.execute("CREATE TABLE IF NOT EXISTS emb "
                        "(k TEXT PRIMARY KEY, model TEXT, dim INT, vec BLOB)")
            con.commit()
            con.close()
            self.enabled = True
        except Exception:  # noqa: BLE001
            self.enabled = False

    @staticmethod
    def key(model: str, text: str) -> str:
        import hashlib
        return hashlib.sha1(f"{model}||{text}".encode("utf-8", "ignore")).hexdigest()

    def get_many(self, model: str, texts: list) -> dict:
        if not self.enabled:
            return {}
        out: dict = {}
        for t in texts:
            k = self.key(model, t)
            if k in self._mem:
                out[k] = self._mem[k]
        if not out and texts:
            try:
                import sqlite3
                keys = [self.key(model, t) for t in texts]
                con = sqlite3.connect(self.path)
                rows = con.execute(
                    "SELECT k, vec FROM emb WHERE k IN (%s)" % ",".join("?" * len(keys)),
                    keys).fetchall()
                con.close()
                import numpy as _np
                for k, blob in rows:
                    v = _np.frombuffer(blob, dtype=_np.float32).copy()
                    self._mem[k] = v
                    out[k] = v
            except Exception:  # noqa: BLE001
                pass
        # map back to text keys present
        hit: dict = {}
        for t in texts:
            k = self.key(model, t)
            if k in out:
                hit[t] = out[k]
        return hit

    def put_many(self, model: str, texts: list, vecs) -> None:
        try:
            import sqlite3
            con = sqlite3.connect(self.path) if self.enabled else None
            for t, v in zip(texts, vecs):
                k = self.key(model, t)
                self._mem[k] = v
                if con is not None:
                    con.execute("INSERT OR REPLACE INTO emb VALUES (?,?,?,?)",
                                (k, model, len(v), bytes(v.tobytes())))
            if con is not None:
                con.commit()
                con.close()
        except Exception:  # noqa: BLE001
            pass


class Embedder:
    # Ordered real-model fallback chain — modern 2024-2026 checkpoints first,
    # legacy MiniLM last (fallback only). Each must be verified present in the
    # local HF cache before use (never touch network at audit time).
    # Default (2026): nomic-embed-text-v1.5 (137M, CPU 1940 tok/s, Apache-2.0,
    # 8192 ctx) for CPU boxes; BGE-M3 (568M, 8k ctx, 100+ langs,
    # dense+sparse+ColBERT hybrid) / Qwen3-Embedding-0.6B (#1 MTEB, 32k ctx)
    # when cached. MiniLM kept as last-resort fallback only.
    FALLBACK_CHAIN = [
        "nomic-ai/nomic-embed-text-v1.5",
        "BAAI/bge-m3",
        "Qwen/Qwen3-Embedding-0.6B",
        "BAAI/bge-small-en-v1.5",
        "sentence-transformers/all-mpnet-base-v2",
        "sentence-transformers/all-MiniLM-L6-v2",
    ]
    # Canonical default for new configs (CPU-friendly, permissively licensed).
    MODERN_DEFAULT = "nomic-ai/nomic-embed-text-v1.5"
    LEGACY_DEFAULT = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, model_name: str, use_fallback: bool = False,
                 require_real: bool = False, cache_dir: str = "",
                 allow_tfidf_fallback: bool = False) -> None:
        self.model_name = model_name or self.MODERN_DEFAULT
        self._model = None
        self._vec = None  # fallback vectorizer
        self.used_model = None  # exact checkpoint actually loaded (for auditing)
        self._kind = "sentence-transformers"
        self._cache = _EmbedCache(cache_dir)
        if use_fallback:
            if require_real and not allow_tfidf_fallback:
                raise RuntimeError(
                    "require_real_models=True forbids the TF-IDF/hashing fallback. "
                    "Pre-cache a real sentence-transformers checkpoint or set "
                    "RAGEVDA_ALLOW_FALLBACK=1 / allow_tfidf_fallback=True for "
                    "explicit triage-only runs."
                )
            self._init_fallback()
            return
        self._init_transformers(require_real=require_real)

    # ------------------------------------------------------------------
    def _locally_cached(self, model_name: str) -> bool:
        """Return True when a model snapshot is already in the local HF cache
        (i.e. can be loaded without any network round-trip)."""
        try:
            from huggingface_hub import try_to_load_from_cache

            candidates = ["model.safetensors", "pytorch_model.bin", "modules.json"]
            return any(
                try_to_load_from_cache(model_name, fname) for fname in candidates
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("cache probe failed for %s: %s", model_name, exc)
            return False

    def _init_transformers(self, require_real: bool = False) -> None:
        import os as _os
        from sentence_transformers import SentenceTransformer

        candidates = [self.model_name] + [
            m for m in self.FALLBACK_CHAIN if m != self.model_name
        ]

        # Load strictly from the local cache (the models were verified cached)
        # so a transient network failure or missing/gated HF repo can never
        # abort the audit mid-run.
        _prev_offline = _os.environ.get("HF_HUB_OFFLINE")
        _prev_endpoint = _os.environ.get("HF_ENDPOINT")
        _os.environ["HF_HUB_OFFLINE"] = "1"
        try:
            return self._try_cached_transformers(
                SentenceTransformer, candidates, require_real)
        finally:
            if _prev_offline is None:
                _os.environ.pop("HF_HUB_OFFLINE", None)
            else:
                _os.environ["HF_HUB_OFFLINE"] = _prev_offline
            if _prev_endpoint is None:
                _os.environ.pop("HF_ENDPOINT", None)
            else:
                _os.environ["HF_ENDPOINT"] = _prev_endpoint

    def _try_cached_transformers(self, SentenceTransformer, candidates,
                                 require_real: bool) -> None:
        for cand in candidates:
            if not self._locally_cached(cand):
                logger.info("embedding model %s not in local cache; skip", cand)
                continue
            try:
                logger.info("loading embedding model %s", cand)
                self._model = SentenceTransformer(cand)
                self.used_model = cand
                self._kind = "sentence-transformers"
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "cached embedding model %s failed to load (%s); trying next",
                    cand, exc,
                )
        # Exhausted every real candidate.
        if require_real:
            # Never silently emit degraded numbers: fail loudly so the report
            # cannot be mistaken for a verified real run.
            import os as _os2
            if _os2.environ.get("RAGEVDA_ALLOW_FALLBACK", "") == "1":
                logger.warning("RAGEVDA_ALLOW_FALLBACK=1: explicit triage fallback")
                self._init_fallback()
                return
            raise RuntimeError(
                f"Real embedding model {self.model_name!r} is required "
                f"(require_real_models=True) but no locally-cached real "
                f"sentence-transformers checkpoint could be loaded "
                f"({candidates}). Download one of these models first, or pick "
                f"an embedding model already present in the local cache."
            )
        logger.warning(
            "Could not load any locally-cached sentence-transformers model "
            "(requested %s). Falling back to local TF-IDF embedding "
            "(LOWER CONFIDENCE).",
            self.model_name,
        )
        self._init_fallback()

    # ------------------------------------------------------------------
    def _init_fallback(self):
        try:
            from sklearn.feature_extraction.text import HashingVectorizer
            from sklearn.preprocessing import Normalizer

            self._vec = HashingVectorizer(
                n_features=4096, alternate_sign=False, norm=None, ngram_range=(1, 2)
            )
            self._norm = Normalizer(norm="l2")
            self._kind = "tfidf-fallback"
            logger.info("using TF-IDF/hashing fallback embedder")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Neither sentence-transformers nor scikit-learn is available. "
                "Install with: pip install sentence-transformers scikit-learn"
            ) from exc

    # ------------------------------------------------------------------
    def encode(self, texts: Iterable[str], batch_size: int = 32,
               show_progress: bool = False) -> np.ndarray:
        texts = [t if isinstance(t, str) else str(t) for t in texts]
        texts = [t if t.strip() else " " for t in texts]
        if self._kind == "sentence-transformers":
            # SQLite cache: skip re-encoding identical (model,text) pairs.
            cached = self._cache.get_many(self.used_model or self.model_name, texts)
            missing_idx = [i for i, t in enumerate(texts) if t not in cached]
            vecs: list = [None] * len(texts)  # type: ignore[list-item]
            for i, t in enumerate(texts):
                if t in cached:
                    vecs[i] = cached[t]
            if missing_idx:
                miss = [texts[i] for i in missing_idx]
                fresh = self._model.encode(
                    miss, batch_size=batch_size, show_progress_bar=show_progress,
                    convert_to_numpy=True, normalize_embeddings=True,
                )
                fresh = np.asarray(fresh, dtype=np.float32)
                self._cache.put_many(self.used_model or self.model_name, miss, fresh)
                for i, v in zip(missing_idx, fresh):
                    vecs[i] = v
            return np.asarray(vecs, dtype=np.float32)
        # fallback
        mats = self._vec.transform(texts)
        mats = self._norm.transform(mats)
        return np.asarray(mats.todense(), dtype=np.float32)

    @staticmethod
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        a = np.asarray(a, dtype=np.float32).ravel()
        b = np.asarray(b, dtype=np.float32).ravel()
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def kind(self) -> str:
        return self._kind