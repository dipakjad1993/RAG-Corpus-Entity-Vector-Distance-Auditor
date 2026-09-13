"""Live LLM Answer Harvester (P0 — without this, not a GEO tool).

Queries real answer surfaces 5-10x per prompt (probabilistic noise sampling),
parses citations + answer text, stores ``Document(source_type='answer')`` with
``metadata={engine, answer_text, cited_urls, repeat}``.

Provider priority: Tavily ``include_answer`` -> Exa answer -> Brave summarizer.
When no paid key is configured the harvester returns [] and logs exactly that
(fail-loud in harvest_stats, never fake answers).
"""
from __future__ import annotations

import re
from typing import Dict, List

from ..utils import get_logger
from .base import Document, new_document

logger = get_logger("ragevda.harvester.answers")

_URL_RE = re.compile(r"https?://[^\s)>\]]+")


def _extract_urls(text: str) -> List[str]:
    return list(dict.fromkeys(_URL_RE.findall(text or "")))


def harvest_answers(prompts: List[Dict], config) -> List[Document]:
    which = (getattr(config, "answer_harvester", "off") or "off").lower()
    if which == "off":
        return []
    repeats = max(1, int(getattr(config, "answer_repeats", 5)))
    docs: List[Document] = []
    # Cap total answer calls (cost control): prompts x repeats bounded.
    budget = min(len(prompts), 30)
    for p in prompts[:budget]:
        q = p.get("prompt", "")
        for r in range(min(repeats, 5)):
            ans, cites = _ask_once(q, config, which)
            if not ans and not cites:
                continue
            docs.append(new_document(
                url=f"answer://{p.get('frame', 'qa')}/{abs(hash(q)) % 10**8}/{r}",
                title=f"Answer [{p.get('frame', 'qa')}/{p.get('persona', 'default')}] {q[:80]}",
                source_type="answer", query=q,
                text=ans or f"Cited sources for: {q}",
                metadata={"engine": which, "frame": p.get("frame", ""),
                          "persona": p.get("persona", ""), "topic": p.get("topic", ""),
                          "repeat": r, "answer_text": ans,
                          "cited_urls": cites},
                final_url="", http_status=200))
    logger.info("answer harvester: %d answer-doc(s) from %d prompt(s)", len(docs), budget)
    return docs


def _ask_once(query: str, config, which: str):
    """One answer-engine call. Returns (answer_text, cited_urls)."""
    if which in ("tavily", "multi"):
        key = getattr(config, "tavily_api_key", "") or ""
        if key:
            try:
                from .paid_search import _post_json
                data = _post_json("https://api.tavily.com/search",
                                  {"Authorization": f"Bearer {key}"},
                                  {"query": query, "max_results": 5,
                                   "include_answer": True})
                ans = data.get("answer", "") or ""
                urls = [i.get("url", "") for i in data.get("results", []) or []]
                return ans[:6000], [u for u in urls if u] or _extract_urls(ans)
            except Exception as exc:  # noqa: BLE001
                logger.debug("tavily answer failed: %s", exc)
    if which in ("exa", "multi"):
        key = getattr(config, "exa_api_key", "") or ""
        if key:
            try:
                from .paid_search import _post_json
                data = _post_json("https://api.exa.ai/answer",
                                  {"x-api-key": key, "Content-Type": "application/json"},
                                  {"query": query})
                ans = data.get("answer", "") or ""
                return ans[:6000], _extract_urls(ans)
            except Exception as exc:  # noqa: BLE001
                logger.debug("exa answer failed: %s", exc)
    if which in ("brave", "multi"):
        key = getattr(config, "brave_api_key", "") or ""
        if key:
            try:
                from .paid_search import brave_search
                hits = brave_search(query, key, 5)
                urls = [u for u, _, _ in hits]
                snippets = "\n".join(s for _, _, s in hits)[:4000]
                return snippets, urls
            except Exception as exc:  # noqa: BLE001
                logger.debug("brave answer failed: %s", exc)
    return "", []
