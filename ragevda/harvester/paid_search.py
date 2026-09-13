"""Paid search APIs: Brave / Tavily / Exa (primary live sources).

DDG HTML scraping is legally grey + breaks weekly — it is FALLBACK ONLY now.
Primary live order: SearXNG (self-hosted) -> Brave/Tavily/Exa (keyed APIs) ->
Reddit/YouTube/TikTok UGC -> DDG fallback. Each client returns normalized
``(url, title, snippet)`` lists; the orchestrator fetches + cleans pages.
Keys from config or env (BRAVE_API_KEY / TAVILY_API_KEY / EXA_API_KEY).
All fail-open (empty list on missing key / network error) — never abort audit.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from ..utils import get_logger

logger = get_logger("ragevda.harvester.paid_search")


def _post_json(url: str, headers: Dict, payload: Dict, timeout: int = 20) -> Dict:
    import httpx
    from ..utils import assert_url_allowed
    assert_url_allowed(url)
    with httpx.Client(timeout=timeout) as c:
        r = c.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()


def brave_search(query: str, api_key: str = "", count: int = 10) -> List[Tuple[str, str, str]]:
    if not api_key:
        return []
    try:
        import httpx
        from ..utils import assert_url_allowed
        assert_url_allowed("https://api.search.brave.com/res/v1/web/search")
        with httpx.Client(timeout=20) as c:
            r = c.get("https://api.search.brave.com/res/v1/web/search",
                      headers={"X-Subscription-Token": api_key},
                      params={"q": query, "count": min(20, count)})
            r.raise_for_status()
            data = r.json()
        out = []
        for item in (data.get("web", {}) or {}).get("results", []) or []:
            out.append((item.get("url", ""), item.get("title", ""),
                        item.get("description", "")))
        return [t for t in out if t[0]]
    except Exception as exc:  # noqa: BLE001
        logger.warning("brave search failed for %r: %s", query, exc)
        return []


def tavily_search(query: str, api_key: str = "", max_results: int = 10) -> List[Tuple[str, str, str]]:
    if not api_key:
        return []
    try:
        data = _post_json("https://api.tavily.com/search",
                          {"Authorization": f"Bearer {api_key}"},
                          {"query": query, "max_results": max_results,
                           "include_answer": True})
        out = []
        for item in data.get("results", []) or []:
            out.append((item.get("url", ""), item.get("title", ""),
                        item.get("content", "")[:2000]))
        return [t for t in out if t[0]]
    except Exception as exc:  # noqa: BLE001
        logger.warning("tavily search failed for %r: %s", query, exc)
        return []


def exa_search(query: str, api_key: str = "", count: int = 10) -> List[Tuple[str, str, str]]:
    if not api_key:
        return []
    try:
        data = _post_json("https://api.exa.ai/search",
                          {"x-api-key": api_key, "Content-Type": "application/json"},
                          {"query": query, "numResults": count,
                           "contents": {"text": {"maxCharacters": 2000}}})
        out = []
        for item in data.get("results", []) or []:
            out.append((item.get("url", ""), item.get("title", ""),
                        (item.get("text", "") or "")[:2000]))
        return [t for t in out if t[0]]
    except Exception as exc:  # noqa: BLE001
        logger.warning("exa search failed for %r: %s", query, exc)
        return []


def multi_search(query: str, config, count: int = 10) -> List[Tuple[str, str, str]]:
    """Fan out across every configured paid API; de-dupe by URL."""
    out: List[Tuple[str, str, str]] = []
    out += brave_search(query, getattr(config, "brave_api_key", "") or "", count)
    out += tavily_search(query, getattr(config, "tavily_api_key", "") or "", count)
    out += exa_search(query, getattr(config, "exa_api_key", "") or "", count)
    seen, uniq = set(), []
    for u, t, s in out:
        if u.lower() in seen:
            continue
        seen.add(u.lower())
        uniq.append((u, t, s))
    return uniq
