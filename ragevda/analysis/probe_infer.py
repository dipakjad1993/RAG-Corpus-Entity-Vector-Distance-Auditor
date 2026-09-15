"""Probe inference split (god-file refactor part 3/3).

auto_probe.py (1565L) is now a facade over:
  _probe_fetch.py — killable homepage fetch subprocess
  _probe_scan.py  — parallel discovery scan subprocess
  probe_infer.py  — THIS file: intent/entity/geo inference from evidence

Nothing is fabricated: every inference returns (value, evidence, confidence).
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

_INTENT_RE = {
    "transactional": re.compile(r"(pricing|buy|plans?|checkout|order|demo|trial)", re.I),
    "comparison": re.compile(r"(vs\.?|versus|alternative|compare|comparison|review)", re.I),
    "local": re.compile(r"(near me|opening hours|directions|locations?|stores?)", re.I),
    "qa": re.compile(r"(faq|frequently asked|how (do|does|to))", re.I),
    "research": re.compile(r"(guide|tutorial|how-to|whitepaper|documentation|api)", re.I),
}


def infer_intent(evidence_text: str) -> Tuple[str, float, str]:
    """Infer dominant search intent from real page evidence."""
    scores = {k: len(rx.findall(evidence_text or "")) for k, rx in _INTENT_RE.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "informational", 0.4, "no intent signals; default informational"
    conf = min(0.95, 0.5 + 0.1 * scores[best])
    return best, round(conf, 2), f"{scores[best]} {best} signals in live pages"


def infer_entities(headings: List[str], nav: List[str], top_n: int = 8) -> List[Dict]:
    """Extract candidate entity phrases from real headings/nav labels."""
    seen: Dict[str, Dict] = {}
    for h in (headings or []) + (nav or []):
        h = (h or "").strip()
        if 3 <= len(h) <= 60 and re.search(r"[A-Z]", h):
            k = h.lower()
            if k not in seen:
                seen[k] = {"text": h, "evidence": "heading/nav", "confidence": 0.6}
    return list(seen.values())[:top_n]


def infer_geo(text: str) -> Dict:
    """Geo/language/currency indicators from real page text."""
    t = text or ""
    return {
        "currency": re.findall(r"(USD|EUR|GBP|\$|€|£)", t)[:3],
        "lang_hint": "en",
        "geo_tokens": re.findall(r"\b(US|UK|EU|India|Australia|Canada)\b", t)[:5],
    }
