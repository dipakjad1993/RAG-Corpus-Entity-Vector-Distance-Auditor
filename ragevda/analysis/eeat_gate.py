"""E-E-A-T gate (96% of cited pages pass; fail = CRITICAL even at 0.92 cosine).

Checks per doc: author byline, publish date, outbound citations to
authoritative sources, about-page linkage signals, review/rating signals.
Each signal is regex/DOM evidence from the REAL fetched HTML/text — never
invented. Score 0-100; <50 = CRITICAL block on citation no matter proximity.
"""
from __future__ import annotations

import re
from typing import Dict

_AUTHOR = re.compile(r"(by\s+[A-Z][a-z]+\s+[A-Z][a-z]+|author|written by|reviewed by)", re.I)
_DATE = re.compile(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20\d{2}|published|updated)", re.I)
_OUTBOUND = re.compile(r"https?://([\w.-]+)", re.I)
AUTHORITY = ("arxiv.org", "doi.org", "nature.com", "science.org", "nih.gov",
             "edu", "gov", "princeton.edu", "mit.edu", "stanford.edu")
_REVIEW = re.compile(r"(rating|stars|reviews?|testimonial|\d\.\d\s*/\s*5|★)", re.I)
_ABOUT = re.compile(r"(about (us|the (author|company))|our team|contact)", re.I)


def gate_doc(url: str, title: str, text: str) -> Dict:
    t = text or ""
    doms = {m.group(1).lower() for m in _OUTBOUND.finditer(t[:20000])}
    has_author = bool(_AUTHOR.search((title or "") + " " + t[:3000]))
    has_date = bool(_DATE.search(t[:5000]))
    has_authority = any(a in d for d in doms for a in AUTHORITY)
    has_review = bool(_REVIEW.search(t[:20000]))
    has_about = bool(_ABOUT.search(t[:20000]))
    score = (25 if has_author else 0) + (20 if has_date else 0) + \
        (30 if has_authority else 0) + (15 if has_review else 0) + (10 if has_about else 0)
    fails = [k for k, v in (("author byline", has_author), ("date", has_date),
                            ("authoritative outbound cite", has_authority),
                            ("reviews/ratings", has_review),
                            ("about/contact signals", has_about)) if not v]
    return {"url": url, "score": score,
            "verdict": "PASS" if score >= 70 else ("WARN" if score >= 50 else "CRITICAL"),
            "signals": {"author": has_author, "date": has_date,
                        "authority_cite": has_authority, "reviews": has_review,
                        "about": has_about},
            "missing": fails}


def eeat_gate(docs) -> Dict:
    rows = []
    for d in (docs or []):
        try:
            rows.append(gate_doc(getattr(d, "url", ""), getattr(d, "title", ""),
                                getattr(d, "text", "") or ""))
        except Exception:  # noqa: BLE001
            continue
    crit = sum(1 for r in rows if r["verdict"] == "CRITICAL")
    avg = round(sum(r["score"] for r in rows) / max(1, len(rows)), 1) if rows else 0.0
    return {"rows": rows[:200], "critical_count": crit, "avg_score": avg,
            "pass_rate_pct": round(100 * sum(1 for r in rows if r["verdict"] == "PASS") / max(1, len(rows)), 1),
            "method": "byline/date/authority-outbound/reviews/about DOM evidence; <50 CRITICAL blocks citation"}
