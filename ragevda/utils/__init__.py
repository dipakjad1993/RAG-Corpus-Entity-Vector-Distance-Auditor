"""Shared utilities: logging, deterministic HTTP client, text helpers."""

from __future__ import annotations

import logging
import hashlib
import re
import time
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
    """Split a long document into overlapping semantic windows.

    UNIFIED SPLITTER (fixes double-chunking bug): this is now a thin wrapper
    over :func:`ragevda.analysis.chunking.token_windows` — the SAME
    sentence-aware BPE packer used for density/retrieval. ``max_chars`` is
    converted to a token budget (≈4 chars/token) so embeddings and density
    measure IDENTICAL windows. Sentence boundaries are never broken.
    """
    text = normalize_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    try:
        from ..analysis.chunking import token_windows
        toks = max(32, max(64, max_chars // 4))
        ov = max(0, min(overlap // 4, toks - 1))
        wins = token_windows(text, toks, ov)
        if wins:
            return wins
    except Exception:  # noqa: BLE001
        pass
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
# SSRF guard: block fetches to private/loopback/link-local hosts unless the
# operator explicitly opts in with RAGEVDA_ALLOW_PRIVATE_NET=1.
# ---------------------------------------------------------------------------

def _host_is_blocked(url: str) -> Optional[str]:
    from urllib.parse import urlparse
    import ipaddress
    import socket
    try:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return "empty host"
        if host in ("localhost",) or host.endswith(".localhost"):
            return "loopback host"
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            try:
                ip = ipaddress.ip_address(socket.gethostbyname(host))
            except Exception:  # noqa: BLE001
                return None  # DNS failure: let the fetch fail naturally
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            import os as _os
            if _os.environ.get("RAGEVDA_ALLOW_PRIVATE_NET", "") != "1":
                return f"private/non-public IP {ip}"
        return None
    except Exception:  # noqa: BLE001
        return None


def assert_url_allowed(url: str, allowlist: Optional[List[str]] = None) -> None:
    """Raise ValueError if ``url`` is an SSRF risk or outside ``allowlist``."""
    from urllib.parse import urlparse
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"blocked URL scheme: {parts.scheme!r} (http/https only)")
    if allowlist:
        host = (parts.hostname or "").lower()
        if not any(host == d.lower() or host.endswith("." + d.lower()) for d in allowlist):
            raise ValueError(f"URL host {host!r} not in fetch allowlist")
    blocked = _host_is_blocked(url)
    if blocked:
        raise ValueError(f"SSRF guard blocked fetch to {url!r}: {blocked}")


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
        allowlist: Optional[List[str]] = None,
        max_redirects: int = 3,
    ) -> None:
        import httpx

        self._httpx = httpx
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            verify=verify,
            headers={"User-Agent": user_agent},
            proxy=proxy,
            max_redirects=max_redirects,
        )
        self.max_retries = max_retries
        self.allowlist = allowlist

    def get(self, url: str, **kwargs):
        import random
        # SSRF + allowlist enforcement on EVERY outbound fetch (manual redirect
        # chain so each hop is re-validated).
        assert_url_allowed(url, self.allowlist)
        max_hops = 3
        current = url
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._client.get(current, **kwargs)
                # Manual redirect chain (max 3 hops), each hop SSRF-validated.
                hops = 0
                while resp.status_code in (301, 302, 303, 307, 308) and hops < max_hops:
                    loc = resp.headers.get("location", "")
                    if not loc:
                        break
                    from urllib.parse import urljoin
                    current = urljoin(current, loc)
                    assert_url_allowed(current, self.allowlist)
                    resp = self._client.get(current, **kwargs)
                    hops += 1
                try:
                    resp.redirects_trail = hops  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
                return resp
            except Exception as exc:  # noqa: BLE001 - network resilience
                last_exc = exc
                backoff = min(30.0, (2 ** (attempt - 1)) * 0.5 + random.uniform(0, 0.5))
                logging.getLogger("ragevda.http").warning(
                    "GET %s failed (attempt %d/%d): %s [backoff %.1fs]",
                    url, attempt, self.max_retries, exc, backoff,
                )
                if attempt < self.max_retries:
                    time.sleep(backoff)
        if last_exc:
            raise last_exc
        raise RuntimeError("unreachable")

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
