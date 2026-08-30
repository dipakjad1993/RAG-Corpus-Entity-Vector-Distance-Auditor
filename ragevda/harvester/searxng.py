"""Self-hosted SearXNG harvester.

If the operator runs a local/remote SearXNG instance (free, open-source
metasearch), this harvester queries its JSON API.  This is the most reliable
key-less option because the operator controls the instance and rate limits.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import logging
import time
from typing import Dict, List, Optional

from .base import Document, new_document
from .cleaner import extract_text
from ..utils import HttpClient, get_logger

logger = get_logger("ragevda.harvester.searxng")


class SearXNGHarvester:
    def __init__(self, config) -> None:
        self.config = config
        base = config.searxng_base_url or ""
        self.base = base.rstrip("/")
        self.client = HttpClient(
            timeout=config.request_timeout,
            user_agent=config.user_agent,
            proxy=config.proxy,
        )
        self.stats = {"queries": 0, "empty_queries": 0, "candidates": 0,
                      "fetched": 0}

    def ping(self) -> bool:
        """Connectivity probe: is this SearXNG instance actually reachable?

        A single ``/search`` call (one trivial query) cards out DNS/connectivity
        problems early so the caller can fall back to DuckDuckGo instead of
        retrying every expanded query against a dead endpoint.
        """
        try:
            probe = self.client.get(
                f"{self.base}/search",
                params={"q": "ragevda connectivity probe", "format": "json"},
            )
            return 200 <= probe.status_code < 500
        except Exception:  # noqa: BLE001 - network failure == unreachable
            return False

    def _search(self, query: str, depth: int) -> List[Dict]:
        params = {"q": query, "format": "json", "count": depth}
        if self.config.locality:
            params["language"] = self.config.locality
        try:
            resp = self.client.get(f"{self.base}/search", params=params)
            data = resp.json()
            return data.get("results", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("searxng search failed for %r: %s", query, exc)
            return []

    @staticmethod
    def _classify(url: str) -> str:
        low = url.lower()
        if "reddit.com" in low or "redd.it" in low:
            return "reddit"
        if any(k in low for k in ("news", "/news", "blog")):
            return "news"
        return "web"

    def harvest(self, queries: List[str], depth: Optional[int] = None) -> List[Document]:
        depth = depth or self.config.crawl_depth
        seen: set = set()
        candidates: List[Dict] = []
        for q in queries:
            self.stats["queries"] += 1
            results = self._search(q, depth)
            if not results:
                self.stats["empty_queries"] += 1
            for r in results:
                href = r.get("url") or r.get("link") or ""
                if not href or href in seen:
                    continue
                seen.add(href)
                candidates.append(
                    {"url": href, "title": r.get("title", ""),
                     "source_type": self._classify(href), "query": q}
                )
        self.stats["candidates"] = len(candidates)

        docs: List[Document] = []
        with cf.ThreadPoolExecutor(max_workers=self.config.max_concurrency) as ex:
            futs = {
                ex.submit(self._fetch, c): c for c in candidates
            }
            for fut in cf.as_completed(futs):
                doc = fut.result()
                if doc:
                    docs.append(doc)
        self.stats["fetched"] = len(docs)
        logger.info("searxng harvested %d documents", len(docs))
        return docs

    def _fetch(self, c: Dict) -> Optional[Document]:
        try:
            t0 = time.perf_counter()
            resp = self.client.get(c["url"])
            fetch_ms = (time.perf_counter() - t0) * 1000.0
            status = resp.status_code
            if status != 200:
                return None
            text = extract_text(resp.text, url=c["url"])
            if len(text) < self.config.min_paragraph_chars:
                return None
            content_hash = hashlib.sha1(
                resp.text.encode("utf-8", "ignore")).hexdigest()
            redirects = [r.url for r in getattr(resp, "history", []) if r.url]
            headers = {k.lower(): v for k, v in (resp.headers or {}).items()}
            return new_document(
                url=c["url"], title=c["title"], source_type=c["source_type"],
                query=c["query"], text=text, raw_html=resp.text,
                final_url=resp.url, http_status=status,
                content_hash=content_hash, fetch_ms=round(fetch_ms, 1),
                redirects=redirects, headers=headers,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetch failed %s: %s", c["url"], exc)
            return None

    def close(self) -> None:
        self.client.close()
