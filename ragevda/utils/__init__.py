"""Shared utilities: logging, deterministic HTTP client, text helpers."""

from __future__ import annotations

import logging
import hashlib
import re
import unicodedata
from typing import Iterable, List, Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def get_logger(name: str = "ragevda", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")


def normalize_text(text: str) -> str:
    """Normalize unicode + collapse whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u00a0", " ")
    text = _WS_RE.sub(" ", text).strip()
    return text


def strip_urls(text: str) -> str:
    return _URL_RE.sub(" ", text)


def chunk_text(text: str, max_chars: int = 400, overlap: int = 40) -> List[str]:
    """Split a long document into overlapping character-windows.

    Embedding models have token limits; chunking keeps each embedding focused
    on a semantically coherent slice of the document.  Overlap preserves
    context across boundaries.
    """
    text = normalize_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    step = max(1, max_chars - overlap)
    for start in range(0, len(text), step):
        window = text[start:start + max_chars]
        if len(window) >= 20:
            chunks.append(window)
        if start + max_chars >= len(text):
            break
    return chunks


def make_id(*parts: str) -> str:
    """Deterministic short id from arbitrary string parts."""
    h = hashlib.sha1("||".join(p for p in parts).encode("utf-8")).hexdigest()
    return h[:16]


def safe_filename(name: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")
    return out or "unnamed"


# ---------------------------------------------------------------------------
# Generic HTTP client (sync, with retries)
# ---------------------------------------------------------------------------

class HttpClient:
    """Thin wrapper over httpx with retries, timeout, optional proxy."""

    def __init__(
        self,
        timeout: int = 20,
        max_retries: int = 2,
        user_agent: str = "ragevda/1.0",
        proxy: Optional[str] = None,
        verify: bool = True,
    ) -> None:
        import httpx

        self._httpx = httpx
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            verify=verify,
            headers={"User-Agent": user_agent},
            proxy=proxy,
        )
        self.max_retries = max_retries

    def get(self, url: str, **kwargs):
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._client.get(url, **kwargs)
                return resp
            except Exception as exc:  # noqa: BLE001 - network resilience
                last_exc = exc
                logging.getLogger("ragevda.http").warning(
                    "GET %s failed (attempt %d/%d): %s",
                    url, attempt, self.max_retries, exc,
                )
        if last_exc:
            raise last_exc
        raise RuntimeError("unreachable")

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
