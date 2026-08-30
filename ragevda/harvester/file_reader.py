"""Local corpus reader.

When the operator already has a folder of research (HTML, Markdown, plain
text, PDF) -- or simply wants a deterministic, offline run -- the ``file``
harvester ingests those documents directly.  This makes the tool fully
reproducible and CI-friendly (great for testing without network access).
"""

from __future__ import annotations

import glob
import hashlib
import logging
import os
import time
from typing import List, Optional

from .base import Document, new_document, domain_of
from .cleaner import extract_text
from ..utils import get_logger, normalize_text

logger = get_logger("ragevda.harvester.file")


class FileHarvester:
    SUPPORTED = (".html", ".htm", ".md", ".markdown", ".txt", ".xml")

    def __init__(self, config) -> None:
        self.config = config
        self.stats = {"queries": 0, "empty_queries": 0, "candidates": 0,
                      "fetched": 0}

    def _read_text(self, path: str) -> str:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()

    def harvest(self, queries: Optional[List[str]] = None, depth: Optional[int] = None) -> List[Document]:
        paths: List[str] = []
        roots = []
        if self.config.corpus_dir:
            roots.append(self.config.corpus_dir)
        for f in self.config.corpus_files or []:
            if os.path.isdir(f):
                roots.append(f)
            else:
                paths.append(f)

        for root in roots:
            for ext in self.SUPPORTED:
                paths.extend(glob.glob(os.path.join(root, "**", f"*{ext}"), recursive=True))

        docs: List[Document] = []
        for p in sorted(set(paths)):
            try:
                raw = self._read_text(p)
            except Exception as exc:  # noqa: BLE001
                logger.warning("cannot read %s: %s", p, exc)
                continue
            source_type = "reddit" if "reddit" in p.lower() else "web"
            if p.lower().endswith((".html", ".htm", ".xml")):
                text = extract_text(raw, url=p)
            else:
                text = normalize_text(raw)
            if len(text) < self.config.min_paragraph_chars:
                continue
            content_hash = hashlib.sha1(
                raw.encode("utf-8", "ignore")).hexdigest()
            import datetime
            mtime = datetime.datetime.fromtimestamp(
                os.path.getmtime(p), tz=datetime.timezone.utc)
            last_modified = mtime.strftime("%a, %d %b %Y %H:%M:%S GMT")
            docs.append(
                new_document(
                    url=f"file://{os.path.abspath(p)}",
                    title=os.path.basename(p),
                    source_type=source_type,
                    query="local-corpus",
                    text=text,
                    raw_html=raw if p.lower().endswith((".html", ".htm")) else "",
                    final_url=f"file://{os.path.abspath(p)}",
                    http_status=200,
                    content_hash=content_hash,
                    fetch_ms=0.0,
                    redirects=[],
                    headers={"last-modified": last_modified,
                             "content-type": "text/local-file"},
                )
            )
        logger.info("file harvester loaded %d documents", len(docs))
        self.stats["candidates"] = len(docs)
        self.stats["fetched"] = len(docs)
        return docs

    def close(self) -> None:
        pass
