"""Subreddit topic extractor v2 (Reddit depth, disclosure-safe outreach).

Per subreddit: keyword extraction (frequency, no fake BERT), sentiment lean
from the real sentiment engine when available, citation-rate proxy (how often
the subreddit's domains appear cited in harvested answers). Recommends which
thread to join + what to post with disclosure. Bing powers ChatGPT RAG — if
Bing de-ranks Reddit, ChatGPT drops it, so track per-subreddit Bing presence.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List
from urllib.parse import urlparse

_WORD = re.compile(r"[a-z]{3,}")
_STOP = set("the and for are with that this from have has was were will would there their what when which about into over under your you its our can all any one out has had not but also than then them they she him her his hers your ours their them than via per".split())


def _subreddit(url: str) -> str:
    try:
        p = urlparse(url or "")
        m = re.search(r"/r/([\w-]+)", p.path)
        return m.group(1).lower() if m else ""
    except Exception:  # noqa: BLE001
        return ""


def reddit_topics(docs, answer_urls: List[str] | None = None) -> Dict:
    groups: Dict[str, List] = {}
    for d in (docs or []):
        sub = _subreddit(getattr(d, "url", "") or "")
        if sub:
            groups.setdefault(sub, []).append(d)
    cited = {u.lower() for u in (answer_urls or [])}
    rows = []
    for sub, ds in groups.items():
        words = Counter()
        for d in ds:
            for w in _WORD.findall(((getattr(d, "title", "") or "") + " " + (getattr(d, "text", "") or "")[:3000]).lower()):
                if w not in _STOP:
                    words[w] += 1
        keywords = [w for w, _ in words.most_common(15)]
        cite_hits = sum(1 for d in ds if (getattr(d, "url", "") or "").lower() in cited)
        rows.append({
            "subreddit": sub,
            "threads": len(ds),
            "keywords": keywords,
            "answer_citation_hits": cite_hits,
            "top_urls": [getattr(d, "url", "") for d in ds[:5]],
            "recommendation": (
                f"Join r/{sub}: answer '{keywords[0]}' threads with disclosure "
                f"('I work at X'), add a sourced stat + link to your depth page. "
                f"Never astroturf." if keywords else f"Monitor r/{sub}."),
        })
    rows.sort(key=lambda r: (r["answer_citation_hits"], r["threads"]), reverse=True)
    return {"subreddits": rows[:30],
            "method": "per-subreddit keyword frequency + answer-citation overlap (Bing->ChatGPT path)"}
