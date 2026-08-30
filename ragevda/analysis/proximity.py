"""Feature B analysis: Semantic Vector Proximity Scores.

Computes, for every (entity x topic) pairing, the cosine proximity in vector
space and classifies it (Far / Moderate / Tightly Bound).  Surfaces the
per-topic "brand gap" -- how far the target brand sits from a topic relative
to the strongest competitor already bound to it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .context import AnalysisContext
from ..utils import get_logger

logger = get_logger("ragevda.analysis.proximity")


def classify(score: float, far: float, tight: float) -> str:
    if score >= tight:
        return "Tightly Bound"
    if score >= far:
        return "Moderate"
    return "Far"


def confidence_for(support: int, min_support: int) -> str:
    if support <= 0:
        return "none"
    if support >= min_support:
        return "high"
    if support >= 2:
        return "medium"
    return "low"


def _top_sources(ctx: AnalysisContext, entity: str, topic: str, k: int = 3) -> List[Dict]:
    """Real harvested documents behind a (entity x topic) proximity score."""
    out = []
    for doc_id in ctx.entity_docs.get(entity, set()):
        doc = ctx.doc_by_id.get(doc_id)
        if not doc:
            continue
        sim = ctx.doc_topic_max_sim.get(doc_id, {}).get(topic, 0.0)
        if sim <= 0:
            continue
        out.append({
            "url": doc.url,
            "title": doc.title,
            "source_type": doc.source_type,
            "topic_relevance": round(sim, 4),
        })
    out.sort(key=lambda r: r["topic_relevance"], reverse=True)
    return out[:k]


def analyze_proximity(ctx: AnalysisContext) -> Dict:
    cfg = ctx.config
    rows: List[Dict] = []
    for topic in cfg.industry_topics:
        for ent, stats in ctx.entity_stats.items():
            prox = stats.topic_proximity.get(topic, 0.0)
            support = stats.total_mentions
            rows.append({
                "topic": topic,
                "entity": ent,
                "proximity": round(prox, 4),
                "label": classify(prox, cfg.far_threshold, cfg.tight_binding_threshold),
                "docs_highly_relevant": stats.topic_doc_counts.get(topic, 0),
                "support_mentions": support,
                "confidence": confidence_for(support, cfg.confidence_min_support),
                "threshold_used": ctx.topic_thresholds.get(topic, cfg.high_relevance_threshold),
                "top_sources": _top_sources(ctx, ent, topic),
            })

    # Brand gap per topic: brand proximity vs best competitor proximity
    brand = cfg.target_brand
    gaps: List[Dict] = []
    for topic in cfg.industry_topics:
        brand_prox = ctx.entity_stats[brand].topic_proximity.get(topic, 0.0)
        comp_prox = {
            c: ctx.entity_stats[c].topic_proximity.get(topic, 0.0)
            for c in cfg.competitor_entities
        }
        best_comp = max(comp_prox, key=comp_prox.get) if comp_prox else None
        best_comp_val = comp_prox.get(best_comp, 0.0) if best_comp else 0.0
        gap = round(best_comp_val - brand_prox, 4)
        gaps.append({
            "topic": topic,
            "brand_proximity": round(brand_prox, 4),
            "best_competitor": best_comp,
            "best_competitor_proximity": round(best_comp_val, 4),
            "gap": gap,
            "severity": "critical" if gap >= 0.30 else ("high" if gap >= 0.15 else "low"),
        })

    return {
        "rows": rows,
        "gaps": gaps,
        "thresholds": {
            "far": cfg.far_threshold,
            "tight": cfg.tight_binding_threshold,
        },
        "embedding_kind": ctx.embedding_kind,
    }
