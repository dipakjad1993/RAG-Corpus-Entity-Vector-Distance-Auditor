"""Actionable Off-Page Recommendation generator.

Translates the raw metrics into prioritized, human-readable directives that
an SEO / PR team can execute immediately:

* Pitch targets -- high-relevance publications that already cite competitors
  but omit the brand (unlinked authority gap).
* Community engagement -- Reddit / forum threads ranking as retrieval sources.
* Content / proximity gaps -- topics where the brand is semantically far from
  the cluster and must earn co-citation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .context import AnalysisContext
from ..utils import get_logger

logger = get_logger("ragevda.analysis.recommendations")


@dataclass
class Recommendation:
    rank: int
    priority: str            # P1 / P2 / P3
    category: str
    title: str
    rationale: str
    action: str
    url: Optional[str] = None
    score: float = 0.0


def _priority_label(score: float) -> str:
    if score >= 1.2:
        return "P1"
    if score >= 0.8:
        return "P2"
    return "P3"


def generate(ctx: AnalysisContext, proximity_result: Dict,
             citation_result: Dict, invisibility_result: Dict) -> List[Recommendation]:
    cfg = ctx.config
    brand = cfg.target_brand
    recs: List[Recommendation] = []
    rank = 0

    # ---- Off-page pitch targets --------------------------------------
    targets = citation_result.get("off_page_targets", [])
    for t in targets:
        comp_links = t.get("competitor_links", [])
        comp_any = t.get("competitors_present", [])
        score = t["topic_relevance"] * (1 + len(comp_links)) * \
            (1.2 if t["source_type"] == "news" else 1.0)
        if t.get("high_relevance"):
            score *= 1.3
        comp_str = ", ".join(comp_links) if comp_links else ", ".join(comp_any)
        rec = Recommendation(
            rank=0,
            priority=_priority_label(score),
            category="Off-Page Pitch",
            title=f"Pitch {t['source_type'].upper()} source: {t['title'][:80]}",
            rationale=(
                f"Article is highly relevant to '{t['top_topic']}' "
                f"(vector similarity {t['topic_relevance']:.2f}) and already "
                f"cites competitor(s): {comp_str or 'n/a'} -- but omits {brand}."
            ),
            action=(
                f"Outreach to {t['url']} to earn a citation/link for {brand} in "
                f"the context of '{t['top_topic']}'."
            ),
            url=t["url"],
            score=round(score, 3),
        )
        recs.append(rec)

    # ---- Community engagement (Reddit/forums) -----------------------
    reddit_targets = [t for t in targets if t["source_type"] == "reddit"]
    reddit_targets.sort(key=lambda r: r["topic_relevance"], reverse=True)
    for t in reddit_targets[:5]:
        score = t["topic_relevance"] * 1.1
        recs.append(Recommendation(
            rank=0,
            priority=_priority_label(score),
            category="Community Engagement",
            title=f"Engage thread: {t['title'][:80]}",
            rationale=(
                f"Reddit thread ranks as a retrieval source for '{t['top_topic']}' "
                f"(similarity {t['topic_relevance']:.2f}) and cites "
                f"{', '.join(t.get('competitors_present', [])) or 'competitors'} "
                f"but not {brand}."
            ),
            action=(
                f"Participate authentically in {t['url']} and reference {brand} "
                f"where relevant to '{t['top_topic']}'."
            ),
            url=t["url"],
            score=round(score, 3),
        ))

    # ---- Proximity / content gaps ----------------------------------
    for gap in proximity_result.get("gaps", []):
        if gap["severity"] in ("critical", "high"):
            score = 1.0 + gap["gap"]
            recs.append(Recommendation(
                rank=0,
                priority=_priority_label(score),
                category="Proximity / Content Gap",
                title=f"Close semantic gap on '{gap['topic']}'",
                rationale=(
                    f"{brand} proximity to '{gap['topic']}' is "
                    f"{gap['brand_proximity']:.2f} vs best competitor "
                    f"{gap['best_competitor']} at {gap['best_competitor_proximity']:.2f} "
                    f"(gap {gap['gap']:.2f}, {gap['severity']})."
                ),
                action=(
                    f"Produce/curate content and earn co-citations that bind "
                    f"{brand} to '{gap['topic']}'; target the off-page sources above."
                ),
                score=round(score, 3),
            ))

    # ---- Sort + rank ------------------------------------------------
    recs.sort(key=lambda r: r.score, reverse=True)
    for i, r in enumerate(recs, start=1):
        r.rank = i
    return recs[: cfg.top_n_recommendations]
