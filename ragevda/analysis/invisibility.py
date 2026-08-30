"""RAG Invisibility Index (per-topic) & Vector Share of Voice.

The composite invisibility index lives in :mod:`citation_gap`; this module
breaks it down per target topic and adds a *Vector Share of Voice* metric --
the brand's fraction of presence inside the high-relevance retrieval corpus
relative to its competitors.  Low share-of-voice + high invisibility is the
exact condition under which AI Overviews / SearchGPT exclude the brand.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Dict, List

from .context import AnalysisContext
from ..utils import get_logger

logger = get_logger("ragevda.analysis.invisibility")


def analyze_invisibility(ctx: AnalysisContext, citation_result: Dict) -> Dict:
    cfg = ctx.config
    brand = cfg.target_brand.lower()
    comps = [c.lower() for c in cfg.competitor_entities]
    citations: List = citation_result["citations"]
    per_topic: List[Dict] = []
    for topic in cfg.industry_topics:
        threshold = ctx.topic_thresholds.get(topic, cfg.high_relevance_threshold)
        relevant = 0
        brand_present = 0
        comp_present_total = 0
        comp_counts: Counter = Counter()
        invisible = 0

        for c in citations:
            sim = c.max_topic_sim if c.max_topic == topic else \
                ctx.doc_topic_max_sim.get(c.doc_id, {}).get(topic, 0.0)
            if sim < threshold:
                continue
            relevant += 1
            brand_here = brand not in c.omitted
            comps_here = [comp for comp in comps if comp not in c.omitted]
            if brand_here:
                brand_present += 1
            comp_present_total += len(comps_here)
            for comp in comps_here:
                comp_counts[comp] += 1
            if (not brand_here) and comps_here:
                invisible += 1

        denom = brand_present + comp_present_total
        sov = round(brand_present / denom * 100.0, 2) if denom else 0.0
        inv_pct = round(invisible / relevant * 100.0, 2) if relevant else 0.0

        per_topic.append({
            "topic": topic,
            "relevant_docs": relevant,
            "brand_present_docs": brand_present,
            "competitor_present_docs": comp_present_total,
            "competitor_breakdown": dict(comp_counts),
            "topic_invisibility_pct": inv_pct,
            "vector_share_of_voice_pct": sov,
            "threshold_used": round(threshold, 4),
        })

    # Composite vector share of voice across all topics (presence-weighted)
    total_brand = sum(t["brand_present_docs"] for t in per_topic)
    total_comp = sum(t["competitor_present_docs"] for t in per_topic)
    composite_sov = round(
        total_brand / (total_brand + total_comp) * 100.0, 2
    ) if (total_brand + total_comp) else 0.0

    return {
        "per_topic": per_topic,
        "composite_vector_share_of_voice_pct": composite_sov,
        "composite_invisibility_index_pct": citation_result["rag_invisibility_index"],
    }
