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
    """Fan out across every configured paid API for ONE query; de-dupe by URL."""
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


def _rrf_merge(rank_lists: List[List[Tuple[str, str, str]]], k: int = 60) -> List[Tuple[str, str, str]]:
    """Reciprocal-rank-fuse per-query result lists into one ranked list.

    Real multi-query fan-out: each query contributes a ranked list; a URL
    seen at rank r in any list scores 1/(k+r). Scores sum across lists so
    URLs corroborated by several fan-out queries surface first. Metadata
    (title/snippet) is kept from the highest-scoring occurrence. Pure,
    auditable math — no black-box score.
    """
    scores: Dict[str, float] = {}
    meta: Dict[str, Tuple[str, str, str]] = {}
    for lst in rank_lists:
        for rank, (u, t, s) in enumerate(lst or [], start=1):
            key = (u or "").strip().lower()
            if not key:
                continue
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in meta:
                meta[key] = (u, t, s)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [meta[k] for k, _ in ranked]


def multi_search_all(queries: List[str], config, count: int = 10,
                     max_queries: int = 20) -> List[Tuple[str, str, str]]:
    """Fan out across ALL queries (not just queries[0]) with thread-pool batch.

    * Caps outbound fan-out at ``max_queries`` (API-cost bound) while always
      keeping the primary topic queries first.
    * Runs per-query ``multi_search`` concurrently (ThreadPool, fail-open per
      query) then RRF-merges the ranked lists.
    * Backward compatible: ``multi_search(q, cfg)`` still handles one query.
    """
    from concurrent.futures import ThreadPoolExecutor
    qs = [q for q in (queries or []) if q and q.strip()]
    if not qs:
        return []
    qs = qs[:max(1, max_queries)]
    per_query: List[List[Tuple[str, str, str]]] = []
    max_workers = min(8, len(qs))
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(multi_search, q, config, count) for q in qs]
            for f in futures:
                try:
                    per_query.append(f.result(timeout=60) or [])
                except Exception as exc:  # noqa: BLE001
                    logger.warning("fan-out query failed: %s", exc)
                    per_query.append([])
    except Exception as exc:  # noqa: BLE001
        logger.warning("fan-out pool failed, falling back to serial: %s", exc)
        per_query = []
        for q in qs:
            try:
                per_query.append(multi_search(q, config, count))
            except Exception:  # noqa: BLE001
                per_query.append([])
    merged = _rrf_merge(per_query)
    logger.info("paid fan-out: %d queries -> %d unique URLs (RRF-merged)",
                len(qs), len(merged))
    return merged
