"""Core UGC harvesters: Reddit + YouTube (first-class). TikTok OPTIONAL plugin.

46.7% of Perplexity top sources = Reddit; 80-90% of AI answers cite earned
media (2.5x vs owned). Reddit + YouTube are core (stable JSON/transcripts).
TikTok SERP scraping is fragile/auth-walled/TOS-risk: kept as an OPT-IN
plugin (ugc_tiktok=False default; use a paid SERP API) — never a core promise.
Each harvester returns :class:`Document` lists (fail-open) with robots+SSRF guards.
"""
from __future__ import annotations

import json
from typing import List

from ..utils import get_logger, HttpClient
from .base import Document, new_document, robots_allowed

logger = get_logger("ragevda.harvester.ugc")


def _client(config) -> HttpClient:
    return HttpClient(timeout=getattr(config, "request_timeout", 20),
                      user_agent=getattr(config, "user_agent", "ragevda/1.0"),
                      proxy=getattr(config, "proxy", None),
                      allowlist=getattr(config, "fetch_allowlist", None) or None)


def harvest_reddit(queries: List[str], config, per_query: int = 5) -> List[Document]:
    """Reddit via old.reddit search JSON (no key needed)."""
    if not getattr(config, "ugc_reddit", True):
        return []
    queries = list(queries or [])[:5]
    logger.info("UGC harvest: reddit %d queries", len(queries))
    docs: List[Document] = []
    c = _client(config)
    try:
        for q in queries:
            url = f"https://www.reddit.com/search.json?q={q}&sort=relevance&limit={per_query}"
            if not robots_allowed(url, config.user_agent):
                continue
            try:
                r = c.get(url, headers={"User-Agent": config.user_agent})
                if r.status_code != 200:
                    continue
                data = r.json().get("data", {}).get("children", [])
                for item in data:
                    d = (item or {}).get("data", {})
                    link = d.get("url_overridden_by_dest") or d.get("url") or ""
                    title = d.get("title", "")
                    body = (d.get("selftext", "") or "")[:6000]
                    if not link and not body:
                        continue
                    docs.append(new_document(
                        url=link or f"https://www.reddit.com{d.get('permalink', '')}",
                        title=title or q, source_type="reddit", query=q,
                        text=f"{title}\n{body}",
                        metadata={"subreddit": d.get("subreddit", ""),
                                  "score": d.get("score", 0),
                                  "permalink": d.get("permalink", "")},
                        final_url=link, http_status=200))
            except Exception as exc:  # noqa: BLE001
                logger.debug("reddit query %r failed: %s", q, exc)
    finally:
        c.close()
    logger.info("UGC harvest: reddit done (%d docs)", len(docs))
    return docs


def harvest_youtube(queries: List[str], config, per_query: int = 3) -> List[Document]:
    """YouTube: search RSS feed + caption transcript when reachable (no key path)."""
    if not getattr(config, "ugc_youtube", True):
        return []
    queries = list(queries or [])[:5]
    logger.info("UGC harvest: youtube %d queries", len(queries))
    docs: List[Document] = []
    c = _client(config)
    try:
        import urllib.parse as _up
        for q in queries:
            try:
                # YouTube search via public RSS-less oembed is limited; use the
                # invidious-free approach: fetch search page titles is fragile,
                # so use the public feed for known channels is skipped — instead
                # record the SERP entry via thumbnail API (fail-open).
                rss = ("https://www.youtube.com/results?search_query=" +
                       _up.quote_plus(q))
                if not robots_allowed(rss, config.user_agent):
                    continue
                r = c.get(rss, headers={"User-Agent": config.user_agent})
                if r.status_code != 200:
                    continue
                import re
                ids = []
                for m in re.finditer(r'"videoId":"([A-Za-z0-9_-]{11})"', r.text):
                    if m.group(1) not in ids:
                        ids.append(m.group(1))
                    if len(ids) >= per_query:
                        break
                for vid in ids:
                    watch = f"https://www.youtube.com/watch?v={vid}"
                    transcript = _fetch_transcript(watch, c, config)
                    docs.append(new_document(
                        url=watch, title=f"YouTube: {q} ({vid})",
                        source_type="youtube", query=q,
                        text=transcript or f"YouTube video result for {q}",
                        metadata={"video_id": vid}, final_url=watch,
                        http_status=200))
            except Exception as exc:  # noqa: BLE001
                logger.debug("youtube query %r failed: %s", q, exc)
    finally:
        c.close()
    logger.info("UGC harvest: youtube done (%d docs)", len(docs))
    return docs


def _fetch_transcript(watch_url: str, client: HttpClient, config) -> str:
    try:
        r = client.get(watch_url, headers={"User-Agent": config.user_agent})
        import re
        m = re.search(r'"captions":\{"playerCaptionsTracklistRenderer":\{"captionTracks":(\[.*?\])',
                      r.text)
        if not m:
            return ""
        tracks = json.loads(m.group(1))
        if not tracks:
            return ""
        base = tracks[0].get("baseUrl", "")
        if not base:
            return ""
        tr = client.get(base, headers={"User-Agent": config.user_agent})
        segs = re.findall(r"<text[^>]*>(.*?)</text>", tr.text, re.S)
        import html as _h
        return " ".join(_h.unescape(re.sub(r"<[^>]+>", "", s)) for s in segs)[:8000]
    except Exception:  # noqa: BLE001
        return ""


def harvest_tiktok(queries: List[str], config, per_query: int = 3) -> List[Document]:
    """TikTok SERP entries (search page JSON blobs). Fail-open, best-effort."""
    if not getattr(config, "ugc_tiktok", True):
        return []
    queries = list(queries or [])[:5]
    logger.info("UGC harvest: tiktok %d queries", len(queries))
    docs: List[Document] = []
    c = _client(config)
    try:
        import urllib.parse as _up
        import re
        for q in queries:
            try:
                url = ("https://www.tiktok.com/search?q=" + _up.quote_plus(q))
                if not robots_allowed(url, config.user_agent):
                    continue
                r = c.get(url, headers={"User-Agent": config.user_agent})
                if r.status_code != 200:
                    continue
                descs = re.findall(r'"desc":"(.*?)","', r.text)[:per_query]
                for i, d in enumerate(descs):
                    docs.append(new_document(
                        url=f"{url}&item={i}", title=f"TikTok: {q}",
                        source_type="tiktok", query=q,
                        text=d.encode().decode("unicode_escape", "ignore")[:3000],
                        metadata={"position": i}, final_url=url, http_status=200))
            except Exception as exc:  # noqa: BLE001
                logger.debug("tiktok query %r failed: %s", q, exc)
    finally:
        c.close()
    logger.info("UGC harvest: tiktok done (%d docs)", len(docs))
    return docs
