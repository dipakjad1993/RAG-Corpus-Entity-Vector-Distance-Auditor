"""Passage-BERT citation stealer (2026 non-negotiable P0).

Google AIO method: summary -> generate candidate phrases -> backdoor lookup
in sources. We invert it: take harvested ANSWER texts, chunk candidate docs
to 100-200 token passages, embed with the run's real local embedder, and
find the exact phrase overlap that earned a citation.

Rule (empirical 2026): passage cosine > 0.88 = cite-worthy, < 0.75 = ignore.
Output is a verbatim action: "Add this definitional sentence under H2 X".
No synthetic text — every recommendation quotes a real harvested passage.
"""
from __future__ import annotations

import re
from typing import Dict, List

import numpy as np

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")

CITE_THRESHOLD = 0.88
IGNORE_THRESHOLD = 0.75


def _passages(text: str, target_tokens: int = 150) -> List[str]:
    """Split text into ~100-200 token passages on sentence boundaries."""
    sents = [s.strip() for s in _SENT_SPLIT.split(text or "") if s.strip()]
    out, cur, cur_toks = [], [], 0
    for s in sents:
        toks = max(1, len(s.split()))
        if cur and cur_toks + toks > target_tokens + 50:
            out.append(" ".join(cur))
            cur, cur_toks = [], 0
        cur.append(s)
        cur_toks += toks
    if cur:
        out.append(" ".join(cur))
    return [p for p in out if len(p.split()) >= 20][:40]


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if not na or not nb:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def reverse_citations(answer_texts: List[str], docs, embedder) -> Dict:
    """Map harvested answers -> best matching doc passages.

    Returns {"steals": [...], "method": ...}. Each steal has answer_excerpt,
    doc url/title, passage text, cosine, verdict (steal/consider/ignore) and
    a concrete placement action. Fail-open: empty steals on any error.
    """
    try:
        answers = [a for a in (answer_texts or []) if a and a.strip()][:20]
        if not answers or not docs:
            return {"steals": [], "method": "passage-bert: no answers or docs"}
        ans_vecs = embedder.embed([a[:2000] for a in answers])
        steals = []
        for ai, (atext, avec) in enumerate(zip(answers, ans_vecs)):
            best = None
            for d in docs:
                for p in _passages(getattr(d, "text", "") or ""):
                    try:
                        pv = embedder.embed([p[:2000]])[0]
                    except Exception:
                        continue
                    c = _cos(np.asarray(avec, dtype=float), np.asarray(pv, dtype=float))
                    if best is None or c > best[0]:
                        best = (c, d, p)
            if best is None:
                continue
            c, d, p = best
            verdict = "steal" if c >= CITE_THRESHOLD else ("consider" if c >= IGNORE_THRESHOLD else "ignore")
            first_sent = _SENT_SPLIT.split(p)[0][:220] if p else ""
            steals.append({
                "answer_id": ai,
                "answer_excerpt": atext[:300],
                "doc_url": getattr(d, "url", ""),
                "doc_title": getattr(d, "title", ""),
                "passage": p[:800],
                "cosine": round(c, 4),
                "verdict": verdict,
                "action": (f"Add/reuse this definitional sentence verbatim under an H2 "
                           f"near the top of your page: {first_sent!r}")
                if verdict == "steal" else "No verbatim steal; rewrite for definitional clarity.",
            })
        steals.sort(key=lambda s: s["cosine"], reverse=True)
        return {"steals": steals[:30], "cite_threshold": CITE_THRESHOLD,
                "ignore_threshold": IGNORE_THRESHOLD,
                "method": "passage cosine (100-200 tok) vs harvested answers; >0.88 steal"}
    except Exception as exc:  # noqa: BLE001
        return {"steals": [], "method": f"skipped: {exc}"}
