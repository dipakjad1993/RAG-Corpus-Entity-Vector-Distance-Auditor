"""Query fan-out simulator (Google AI Mode 2026: 1 query -> 8-12 sub-queries).

Takes each prompt-library prompt, expands it to fan-outs (local template
expansion; Ollama LLM expansion when configured), runs hybrid retrieval per
fan-out against the harvested corpus, and scores which of YOUR pages covers
which slice. Output: cluster coverage map. AI Mode rewards topical-depth
clusters, not one money page.
"""
from __future__ import annotations

import re
from typing import Dict, List

FANOUT_TEMPLATES = [
    "{q} explained",
    "{q} step by step guide",
    "{q} pros and cons",
    "{q} vs alternatives",
    "{q} pricing and reviews",
    "{q} latest news 2026",
    "{q} how it works",
    "{q} common mistakes",
    "best {q}",
    "{q} FAQ",
]

_WORD = re.compile(r"[a-z0-9]+")


def _toks(s: str) -> set:
    return set(_WORD.findall((s or "").lower()))


def expand_fanout(prompt: str, n: int = 10, llm_expand=None) -> List[str]:
    """Expand one prompt to n fan-outs. LLM expansion when available."""
    if llm_expand:
        try:
            outs = llm_expand(prompt, n) or []
            outs = [o.strip() for o in outs if o and o.strip()][:n]
            if len(outs) >= max(4, n // 2):
                return outs
        except Exception:  # noqa: BLE001
            pass
    base = (prompt or "").strip()
    return [t.format(q=base) for t in FANOUT_TEMPLATES[:n]]


def fanout_coverage(prompts: List[str], docs, config, n: int = 10) -> Dict:
    """Score per-fan-out lexical coverage by brand-owned docs.

    Coverage signal is BM25-ish token overlap (auditable, no fake vectors):
    for each fan-out, rank docs by overlap, mark whether a brand-domain or
    brand-mentioning doc is in top-3. Fail-open.
    """
    try:
        brand = (getattr(config, "target_brand", "") or "").lower()
        owned = {d.strip().lower() for ds in
                 (getattr(config, "entity_domains", {}).get(getattr(config, "target_brand", ""), []) or [])
                 for d in [ds]}
        clusters = []
        for p in (prompts or [])[:30]:
            fanouts = expand_fanout(p, n)
            slices = []
            for f in fanouts:
                fq = _toks(f)
                ranked = []
                for d in (docs or []):
                    dt = _toks((getattr(d, "title", "") or "") + " " + (getattr(d, "text", "") or "")[:2000])
                    ov = len(fq & dt) / max(1, len(fq))
                    ranked.append((ov, d))
                ranked.sort(key=lambda x: x[0], reverse=True)
                top3 = ranked[:3]
                covered = any(brand in ((getattr(d, "text", "") or "").lower() + getattr(d, "url", "").lower())
                              or (getattr(d, "domain", "") or "").lower() in owned for _, d in top3)
                slices.append({"fanout": f, "covered": bool(covered),
                               "top_overlap": round(top3[0][0], 3) if top3 else 0.0,
                               "top_url": getattr(top3[0][1], "url", "") if top3 else ""})
            cov = sum(1 for s in slices if s["covered"]) / max(1, len(slices))
            clusters.append({"prompt": p, "coverage_pct": round(cov * 100, 1),
                             "slices": slices,
                             "gap": "Add a depth-cluster page per uncovered slice; single money page loses in AI Mode."
                             if cov < 0.7 else "Good depth coverage."})
        avg = round(sum(c["coverage_pct"] for c in clusters) / max(1, len(clusters)), 1) if clusters else 0.0
        return {"clusters": clusters, "avg_coverage_pct": avg,
                "method": "template fan-out x10 + lexical top-3 coverage (Ollama LLM when use_llm)"}
    except Exception as exc:  # noqa: BLE001
        return {"clusters": [], "avg_coverage_pct": 0.0, "method": f"skipped: {exc}"}
