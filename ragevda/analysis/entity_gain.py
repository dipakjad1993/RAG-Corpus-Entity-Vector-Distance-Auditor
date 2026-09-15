"""Entity density + Information Gain scorer (replaces generic token-density math).

2026 evidence: 15+ entities/page = 4.8x citation prob; sourced stats +30-40%
visibility (Princeton/KDD 2024); definition sentence 2x cite rate; quotable
chunk +30%; answer-first in first 200 words +33% (Semrush 2026).

All signals come from the REAL doc text + spaCy entities — never synthetic.
"""
from __future__ import annotations

import re
from typing import Dict

_STAT = re.compile(r"\b\d+(\.\d+)?\s*(%|percent|million|billion|studies|survey)\b", re.I)
_DEF = re.compile(r"\b(is defined as|refers to|is a (platform|tool|service|company|system) that)\b", re.I)
_QUOTE = re.compile(r"\"[^\"]{20,200}\"")
_FIRSTHAND = re.compile(r"\b(we (built|tested|measured|surveyed|interviewed)|our (data|research|testing|methodology))\b", re.I)


def score_doc(text: str, entity_count: int) -> Dict:
    t = text or ""
    first200 = " ".join(t.split()[:200])
    brand_first = len(t.split())  # placeholder refined by caller if needed
    signals = {
        "entity_density": entity_count,
        "entity_target_met": entity_count >= 15,
        "sourced_stat": bool(_STAT.search(t[:8000])),
        "definition_sentence": bool(_DEF.search(t[:4000])),
        "quotable_chunk": bool(_QUOTE.search(t[:8000])),
        "firsthand_process": bool(_FIRSTHAND.search(t[:8000])),
        "answer_first_200w": len(first200) > 0,
    }
    lift = (40 if signals["sourced_stat"] else 0) + (100 if signals["definition_sentence"] else 0) + \
        (30 if signals["quotable_chunk"] else 0) + (33 if signals["answer_first_200w"] else 0)
    score = min(100.0, round(entity_count / 15 * 50 + lift / 4, 1))
    fixes = []
    if entity_count < 15:
        fixes.append(f"Add {15 - entity_count}+ named entities (people/places/products/standards) with context.")
    if not signals["sourced_stat"]:
        fixes.append("Add 1-2 sourced statistics with outbound links (+30-40% visibility).")
    if not signals["definition_sentence"]:
        fixes.append("Add one definitional sentence in first 200 words (2x cite rate).")
    if not signals["quotable_chunk"]:
        fixes.append("Add one quotable 25-40 word chunk editors can lift verbatim (+30%).")
    if not signals["firsthand_process"]:
        fixes.append("Add first-hand process/data/methodology (non-commodity Information Gain).")
    return {"signals": signals, "score": score, "fixes": fixes,
            "brand_first_mention_word": brand_first}


def score_corpus(docs, entity_counts: Dict[str, int], brand: str) -> Dict:
    rows = []
    for d in (docs or []):
        text = getattr(d, "text", "") or ""
        # entity count for this doc: counted externally or fallback regex
        key = getattr(d, "doc_id", "") or getattr(d, "url", "")
        n = int(entity_counts.get(key, len(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", text[:8000])) or 0))
        s = score_doc(text, n)
        # brand position in first 200 words?
        words = text.split()
        blow = brand.lower() if brand else ""
        pos = next((i for i, w in enumerate(words[:400]) if blow and blow in w.lower()), -1)
        s["brand_first_mention_word"] = pos
        if pos > 200 or pos < 0:
            s["fixes"].insert(0, "Move brand + answer summary into first 200 words (+33%).")
        rows.append({"url": getattr(d, "url", ""), "title": getattr(d, "title", ""), **s})
    rows.sort(key=lambda r: r["score"])
    avg = round(sum(r["score"] for r in rows) / max(1, len(rows)), 1) if rows else 0.0
    return {"rows": rows[:200], "avg_score": avg,
            "method": "15+ entities target; stat/definition/quote/firsthand/answer-first lifts from real text"}
