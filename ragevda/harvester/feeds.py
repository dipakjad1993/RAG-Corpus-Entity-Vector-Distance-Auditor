"""Feed, footprint and ground-truth harvester.

Ingests three of the tool's direct inputs without relying on a search engine:

* ``content_feeds`` (competitor / industry RSS or sitemap URLs) — parses each
  feed, then fetches every entry's article URL so newly-published competitor
  content is pulled in near-real-time.
* ``serp_footprints`` (search-engine scraping footprints) — concrete source
  URLs surfaced by specific AI-engine surfaces (Google AI Overview citations,
  Bing Copilot URLs, Perplexity sources) ingested separately and tagged by
  engine, instead of one blended SERP scrape.
* ``corpus_files`` / ``corpus_dir`` (historical ground-truth corpora) — copies
  of the operator's own brand / whitepapers, so the report can compare the
  Internal Brand Perception Vector against the Web RAG Vector.

This harvester is an *augmenter*: it can run alongside the primary search
harvester and its documents are merged into the same corpus.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import List, Optional

from .base import Document, domain_of, new_document
from .cleaner import extract_text
from ..utils import get_logger, HttpClient

logger = get_logger("ragevda.harvester.feeds")


def _clean_url(raw: str) -> str:
    """Normalize a user-supplied URL, stripping Markdown link wrappers
    (``[https://…](https://…)``) and stray whitespace/quote/bracket characters
    so a pasted link always resolves even when copied from a rich editor."""
    if not raw:
        return ""
    url = raw.strip()
    # strip surrounding quotes
    url = url.strip("\"'`")
    # unwrap [label](url) Markdown — take the inside of the trailing parens
    m = re.search(r"\]\(\s*(\S+?)\s*\)$", url)
    if m:
        url = m.group(1)
    # strip trailing punctuation that isn't part of a URL path
    url = url.rstrip(".,;")
    return url


def _parse_feed_urls(resp_text: str) -> List[str]:
    """Extract concrete article/sitemap URLs from an RSS/Atom/sitemap XML body."""
    out: List[str] = []
    for tag in ("<link>", "<loc>", "<guid isPermaLink=\"true\">", "<guid>"):
        start = 0
        while True:
            idx = resp_text.find(tag, start)
            if idx == -1:
                break
            seg = resp_text[idx + len(tag):]
            end = seg.find("</")
            if end != -1:
                url = seg[:end].strip()
                if url and url.startswith("http"):
                    out.append(url)
            start = idx + len(tag) + 1
    # de-dupe preserving order
    seen = set()
    uniq = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


class FeedHarvester:
    """Fetches feeds, footprints and ground-truth docs into documents."""

    def __init__(self, config) -> None:
        self.config = config
        self.client = HttpClient(
            timeout=config.request_timeout,
            user_agent=config.user_agent,
            proxy=config.proxy,
        )
        self.stats = {"queries": 0, "empty_queries": 0, "candidates": 0,
                      "fetched": 0}

    # -- individual URL fetch --------------------------------------------
    def _fetch(self, url: str, title: str, source_type: str,
               query: str) -> Optional[Document]:
        try:
            t0 = time.perf_counter()
            resp = self.client.get(url)
            fetch_ms = (time.perf_counter() - t0) * 1000.0
            if resp.status_code != 200:
                logger.warning("feed fetch %s -> HTTP %d", url, resp.status_code)
                return None
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return None
            text = extract_text(resp.text, url=url)
            if len(text) < self.config.min_paragraph_chars:
                return None
            content_hash = hashlib.sha1(
                resp.text.encode("utf-8", "ignore")).hexdigest()
            redirects = [r.url for r in getattr(resp, "history", []) if r.url]
            headers = {k.lower(): v for k, v in (resp.headers or {}).items()}
            return new_document(
                url=url, title=title, source_type=source_type,
                query=query, text=text, raw_html=resp.text,
                final_url=resp.url, http_status=resp.status_code,
                content_hash=content_hash, fetch_ms=round(fetch_ms, 1),
                redirects=redirects, headers=headers,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("feed fetch failed %s: %s", url, exc)
            return None

    # -- feed (RSS / sitemap) --------------------------------------------
    def _harvest_feeds(self) -> List[Document]:
        docs: List[Document] = []
        feeds = list(self.config.content_feeds or [])
        seen_feed = set()
        for feed in feeds:
            feed = _clean_url(feed)
            if not feed or not feed.startswith("http") or feed in seen_feed:
                continue
            seen_feed.add(feed)
            fname = feed.rsplit("/", 1)[-1][:40]
            try:
                resp = self.client.get(feed, timeout=self.config.request_timeout)
            except Exception as exc:  # noqa: BLE001
                logger.warning("feed unreachable %s: %s", feed, exc)
                continue
            if resp.status_code != 200:
                continue
            urls = _parse_feed_urls(resp.text or "")
            if not urls:
                urls = [feed]  # treat the feed URL itself as a direct document
            for url in urls:
                self.stats["candidates"] += 1
                doc = self._fetch(
                    url,
                    title=f"feed:{fname}",
                    source_type="news",
                    query=f"feed:{feed}",
                )
                if doc:
                    docs.append(doc)
                    self.stats["fetched"] += 1
        return docs

    # -- serp / AI-engine scraping footprints ----------------------------
    def _harvest_footprints(self) -> List[Document]:
        docs: List[Document] = []
        for raw in self.config.serp_footprints or []:
            raw = _clean_url(raw)
            if not raw:
                continue
            # Allow optional "engine|label|url" tagged format.
            parts = raw.split("|")
            url = parts[-1].strip()
            engine = parts[0].strip() if len(parts) >= 2 else "general"
            label = parts[1].strip() if len(parts) >= 3 else ""
            if not url.startswith("http"):
                continue
            self.stats["candidates"] += 1
            meta_query = f"serp:{engine}" + (f":{label}" if label else "")
            doc = self._fetch(
                url,
                title=label or f"footprint:{engine}",
                source_type="web",
                query=meta_query,
            )
            if doc:
                if doc.metadata is None:
                    doc.metadata = {}
                doc.metadata["serp_engine"] = engine
                if label:
                    doc.metadata["serp_label"] = label
                docs.append(doc)
                self.stats["fetched"] += 1
        return docs

    def harvest(self, queries: Optional[List[str]] = None,
                depth: Optional[int] = None) -> List[Document]:
        docs: List[Document] = []
        try:
            docs.extend(self._harvest_feeds())
        except Exception as exc:  # noqa: BLE001
            logger.warning("content-feed harvest failed: %s", exc)
        try:
            docs.extend(self._harvest_footprints())
        except Exception as exc:  # noqa: BLE001
            logger.warning("serp-footprint harvest failed: %s", exc)
        if docs:
            logger.info("feed/footprint harvester added %d document(s)", len(docs))
        return docs

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:  # noqa: BLE001
            pass
