"""Harvester base types and the :class:`Harvester` protocol.

A *Document* is the atomic unit flowing through the pipeline.  Harvesters are
responsible for turning a search query (or a local path) into a list of
cleaned :class:`Document` objects whose ``text`` field contains the pure
body content a RAG crawler would actually ingest.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, runtime_checkable

from ..utils import make_id, get_logger


@dataclass
class Document:
    doc_id: str
    url: str
    title: str
    source_type: str                # web | reddit | news | file
    query: str                      # originating query / label
    text: str = ""
    raw_html: str = ""
    domain: str = ""
    extracted_at: str = ""
    metadata: Dict = field(default_factory=dict)
    # --- harvest provenance / verification (real-fetch evidence) ---
    final_url: str = ""            # URL after redirects (proves what was fetched)
    http_status: int = 0          # HTTP status code of the fetch (0 = unknown)
    content_hash: str = ""        # sha1 of body text (proves content integrity)
    fetch_ms: float = 0.0         # fetch latency in ms (proves a live request)
    redirects: List[str] = field(default_factory=list)
    headers: Dict = field(default_factory=dict)  # real response headers (freshness)

    def short_text(self, n: int = 200) -> str:
        return self.text[:n].replace("\n", " ")


def domain_of(url: str) -> str:
    from urllib.parse import urlparse

    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:  # noqa: BLE001
        return ""


# --- robots.txt politeness (per-domain cache) -------------------------------
_ROBOTS_CACHE: Dict[str, object] = {}


def robots_allowed(url: str, user_agent: str = "*", timeout: float = 8.0) -> bool:
    """Return True when fetching ``url`` is allowed by the site's robots.txt.

    Fail-open: unparseable/missing robots.txt or any fetch error means allowed
    (logged at debug). Results are cached per domain for the process lifetime.
    Uses only the stdlib (``urllib.robotparser``) — no new dependencies.
    """
    from urllib.parse import urlparse
    from urllib.robotparser import RobotFileParser

    try:
        parts = urlparse(url)
        domain = (parts.netloc or "").lower()
        if not domain or parts.scheme not in ("http", "https"):
            return True
        if domain in _ROBOTS_CACHE:
            rp = _ROBOTS_CACHE[domain]
        else:
            rp = RobotFileParser()
            rp.set_url(f"{parts.scheme}://{parts.netloc}/robots.txt")
            try:
                rp.read()
            except Exception:  # noqa: BLE001
                return True
            _ROBOTS_CACHE[domain] = rp
        try:
            return bool(rp.can_fetch(user_agent or "*", url))
        except Exception:  # noqa: BLE001
            return True
    except Exception:  # noqa: BLE001
        return True


@runtime_checkable
class Harvester(Protocol):
    """Implementations turn queries into cleaned documents."""

    def harvest(self, queries: List[str], depth: int) -> List[Document]:
        ...


def new_document(
    url: str,
    title: str,
    source_type: str,
    query: str,
    text: str = "",
    raw_html: str = "",
    metadata: Optional[Dict] = None,
    final_url: str = "",
    http_status: int = 0,
    content_hash: str = "",
    fetch_ms: float = 0.0,
    redirects: Optional[List[str]] = None,
    headers: Optional[Dict] = None,
) -> Document:
    return Document(
        doc_id=make_id(url, query),
        url=url,
        title=title or url,
        source_type=source_type,
        query=query,
        text=text,
        raw_html=raw_html,
        domain=domain_of(url),
        extracted_at=datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        metadata=metadata or {},
        final_url=final_url or url,
        http_status=http_status,
        content_hash=content_hash,
        fetch_ms=fetch_ms,
        redirects=redirects or [],
        headers=headers or {},
    )
