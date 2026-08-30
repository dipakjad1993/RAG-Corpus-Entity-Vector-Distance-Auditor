"""Zero-cost web harvesting via DuckDuckGo.

DuckDuckGo has no official free API, but the community `ddgs` package provides
a lightweight, key-less search client.  When `ddgs` is unavailable we fall
back to scraping the public HTML endpoint.  Either way, every returned URL is
then fetched and cleaned into a :class:`Document` so that the downstream NLP
layer only ever sees genuine article body text.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import logging
import re
import time
from typing import Dict, List, Optional

from .base import Document, new_document, domain_of
from .cleaner import extract_text
from ..utils import HttpClient, get_logger

logger = get_logger("ragevda.harvester.ddg")


def _fallback_queries(query: str) -> List[str]:
    """Build progressively simpler variants of a query that returned 0 results.

    We strip the appended ``news``/``reddit`` suffixes first (the DDG text API
    does not expose a dedicated news vertical), then drop trailing qualifiers so
    a core topic still gets a chance to return pages.
    """
    alts: List[str] = []
    stripped = re.sub(r"\s+(news|reddit)$", "", query, flags=re.IGNORECASE).strip()
    if stripped and stripped != query:
        alts.append(stripped)
    tokens = query.split()
    if len(tokens) > 1:
        alts.append(" ".join(tokens[:-1]))
    if len(tokens) > 2:
        alts.append(" ".join(tokens[:2]))
    seen, out = set(), []
    for a in alts:
        if a and a.lower() not in seen:
            seen.add(a.lower())
            out.append(a)
    return out


def _search_ddgs(query: str, depth: int, region: str):
    """Run a query through the ddgs library. Returns list of result dicts."""
    try:
        from ddgs import DDGS
    except Exception:  # noqa: BLE001
        try:
            from duckduckgo_search import DDGS  # older pkg name
        except Exception:  # noqa: BLE001
            return None

    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, region=region, max_results=depth):
                results.append(r)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ddgs text search failed for %r: %s", query, exc)
        return None
    return results


def _search_html(query: str, depth: int, client: HttpClient, region: str):
    """Fallback: scrape html.duckduckgo.com (GET lite endpoint).

    Used when the ``ddgs`` library raises (e.g. transient DNS/timeout). This is a
    best-effort recovery so a single network blip never costs us an entire query.
    """
    results = []
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse, parse_qs

    try:
        resp = client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query, "kl": region, "b": ""},
        )
        soup = BeautifulSoup(resp.text, "lxml")
        for row in soup.select(".result__body")[:depth]:
            a = row.select_one("a.result__a")
            if not a:
                continue
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if "uddg=" in href:  # DDG wraps redirect urls
                real = parse_qs(urlparse(href).query).get("uddg", [href])[0]
                href = real
            snippet = row.select_one(".result__snippet")
            results.append(
                {"title": title, "href": href,
                 "body": snippet.get_text(strip=True) if snippet else ""}
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("html ddg fallback failed for %r: %s", query, exc)
    return results


def _fetch_and_clean(url: str, title: str, source_type: str, query: str,
                      client: HttpClient, min_chars: int) -> Optional[Document]:
    try:
        t0 = time.perf_counter()
        resp = client.get(url)
        fetch_ms = (time.perf_counter() - t0) * 1000.0
        status = resp.status_code
        if status != 200:
            # Keep a lightweight record so the run is auditable even when a
            # page is missing -- but do not ingest its (absent) body.
            logger.warning("fetch %s -> HTTP %d (skipped)", url, status)
            return None
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            return None
        text = extract_text(resp.text, url=url)
        if len(text) < min_chars:
            return None
        content_hash = hashlib.sha1(
            resp.text.encode("utf-8", "ignore")).hexdigest()
        redirects = [r.url for r in getattr(resp, "history", []) if r.url]
        headers = {k.lower(): v for k, v in (resp.headers or {}).items()}
        return new_document(
            url=url, title=title, source_type=source_type,
            query=query, text=text, raw_html=resp.text,
            final_url=resp.url, http_status=status,
            content_hash=content_hash, fetch_ms=round(fetch_ms, 1),
            redirects=redirects, headers=headers,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch failed %s: %s", url, exc)
        return None


class DuckDuckGoHarvester:
    """DuckDuckGo-backed harvester (no API key required)."""

    def __init__(self, config) -> None:
        self.config = config
        self.client = HttpClient(
            timeout=config.request_timeout,
            user_agent=config.user_agent,
            proxy=config.proxy,
        )
        self.region = self._region_for(config.locality)
        self.stats = {"queries": 0, "empty_queries": 0, "candidates": 0,
                      "fetched": 0}

    @staticmethod
    def _region_for(locality: Optional[str]) -> str:
        if not locality:
            return "wt-wt"
        loc = locality.strip().lower()
        mapping = {
            "us": "us-en", "usa": "us-en", "united states": "us-en",
            "uk": "uk-en", "united kingdom": "uk-en", "gb": "uk-en",
            "ca": "ca-en", "canada": "ca-en",
            "au": "au-en", "australia": "au-en",
            "de": "de-de", "germany": "de-de",
            "fr": "fr-fr", "france": "fr-fr",
            "in": "in-en", "india": "in-en",
        }
        return mapping.get(loc, "wt-wt")

    def _search(self, query: str, depth: int):
        results = _search_ddgs(query, depth, self.region)
        if not results:
            results = _search_html(query, depth, self.client, self.region)
        return results or []

    def harvest(self, queries: List[str], depth: Optional[int] = None) -> List[Document]:
        depth = depth or self.config.crawl_depth
        seen_urls: set = set()
        fetched: List[Document] = []
        # Hard cap prevents a run from exploding, but it is user-configurable
        # via ``max_pages`` (0 = unlimited).
        max_pages = self.config.max_pages or 0

        # Phase 1: collect candidate URLs per query, with per-query fallback so
        # a 0-result expanded query (e.g. "... news") still yields pages.
        candidates: List[Dict] = []
        empty_queries = 0
        for q in queries:
            self.stats["queries"] += 1
            res = self._search(q, depth)
            if not res:
                for alt in _fallback_queries(q):
                    res = self._search(alt, depth)
                    if res:
                        logger.info("query %r -> 0; fallback %r -> %d",
                                    q, alt, len(res))
                        q = f"{q} | alt:{alt}"
                        break
            if not res:
                empty_queries += 1
                logger.warning("query %r -> 0 raw results (skipped, no fallback)",
                               q)
                continue
            logger.info("query %r -> %d raw results", q, len(res))
            for r in res:
                href = r.get("href") or r.get("url") or ""
                if not href or href in seen_urls:
                    continue
                if href.startswith("http") is False:
                    continue
                seen_urls.add(href)
                candidates.append(
                    {"url": href, "title": r.get("title", ""),
                     "source_type": self._classify(href, q),
                     "query": q}
                )

        # Cap total pages while preserving query diversity (round-robin).
        if max_pages and len(candidates) > max_pages:
            by_query: Dict[str, List[Dict]] = {}
            for c in candidates:
                by_query.setdefault(c["query"], []).append(c)
            qs = list(by_query.keys())
            trimmed: List[Dict] = []
            while len(trimmed) < max_pages and any(by_query[q] for q in qs):
                for q in qs:
                    if by_query[q]:
                        trimmed.append(by_query[q].pop(0))
                        if len(trimmed) >= max_pages:
                            break
            logger.info("capped candidates %d -> %d (max_pages; set max_pages=0 for unlimited)",
                        len(candidates), len(trimmed))
            candidates = trimmed
        elif max_pages == 0:
            logger.info("no page cap (max_pages=0); fetching all %d candidates",
                        len(candidates))
        self.stats["empty_queries"] = self.stats.get("empty_queries", 0) + empty_queries
        self.stats["candidates"] = len(candidates)
        if empty_queries:
            logger.warning("%d/%d queries returned 0 results even after fallback",
                           empty_queries, len(queries))

        logger.info("fetching %d unique candidate URLs", len(candidates))

        # Phase 2: fetch + clean concurrently.
        with cf.ThreadPoolExecutor(max_workers=self.config.max_concurrency) as ex:
            futures = {
                ex.submit(
                    _fetch_and_clean, c["url"], c["title"], c["source_type"],
                    c["query"], self.client, self.config.min_paragraph_chars,
                ): c
                for c in candidates
            }
            done = 0
            for fut in cf.as_completed(futures):
                doc = fut.result()
                if doc is not None:
                    fetched.append(doc)
                done += 1
                if done % 10 == 0:
                    logger.info("fetched %d/%d pages", done, len(candidates))

        logger.info("harvested %d clean documents", len(fetched))
        self.stats["fetched"] = len(fetched)
        return fetched

    def _classify(self, url: str, query: str) -> str:
        low = url.lower()
        if "reddit.com" in low or "redd.it" in low:
            return "reddit"
        if any(k in low for k in ("news", "article", "/news", "blog")):
            return "news"
        return "web"

    def close(self) -> None:
        self.client.close()
