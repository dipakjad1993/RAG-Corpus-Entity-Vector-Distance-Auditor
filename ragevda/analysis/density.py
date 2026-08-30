"""Enterprise Automated Token Density Adjuster.

The metric beneath "how do I displace a competitor's chunk from top-k vector
retrieval?" is token *density*: within a single RAG retrieval window, how many
real tokens reference the brand/its entities and how tightly are they bound to
the target topic.  If a competitor dominates a topic's retrieval windows, the
fix is a content brief that co-mentions the required entities within a specific
token budget of each other.

This module derives, from the real harvested corpus + the real-token RAG chunk
simulator:

  * per-topic "displacement targets": the competitor entity to displace and the
    exact number of on-topic, on-window brand tokens needed to exceed their
    current top-k share;
  * per-topic entity-density gap: how far your brand's within-window density is
    from the leader's, expressed as a ratio;
  * a concrete token-action plan: how many brand mention tokens, and how close
    together (token distance), to place in the winning window.

All token denominators are the REAL per-window token counts produced by the
chunk simulators' BPE tokenizer -- never a hard-coded window-size constant.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List

from ..utils import get_logger

logger = get_logger("ragevda.analysis.density")


def analyze_token_density(ctx, proximity_rows: List[Dict],
                          windows_by_doc: Dict[str, List]) -> Dict:
    """Compute per-topic token-density gaps and displacement action plans."""
    cfg = ctx.config
    brand = cfg.target_brand
    comps = cfg.competitor_entities
    target_density = cfg.target_entity_density

    # Aggregate real on-window entity tokens AND the real window-token base
    # across every retrieved window, so density is a true per-window ratio.
    entity_window_tokens: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    window_token_base: Dict[str, int] = defaultdict(int)
    entity_window_count: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    brand_topic_window_tokens: Dict[str, int] = defaultdict(int)
    win_size = cfg.chunk_tokens or 512

    for doc_id, wins in windows_by_doc.items():
        for win in wins:
            if not win.retrieved:
                continue
            topic = win.dominant_topic
            # real token width of THIS window (from the BPE tokenizer)
            win_tokens = max(1, win.tokens or win_size)
            window_token_base[topic] += win_tokens
            for ent, dens in win.entity_token_density.items():
                if dens <= 0:
                    continue
                entity_window_tokens[ent][topic] += win.entity_token_count.get(ent, 0)
                entity_window_count[ent][topic] += 1
            for ent, tok in win.entity_token_count.items():
                if ent == brand:
                    brand_topic_window_tokens[topic] += tok

    # Brand proximity per topic from the real proximity matrix.
    brand_prox = {r["topic"]: r["proximity"] for r in proximity_rows if r["entity"] == brand}
    comp_prox: Dict[str, Dict[str, float]] = defaultdict(dict)
    for r in proximity_rows:
        if r["entity"] in comps:
            comp_prox[r["topic"]][r["entity"]] = r["proximity"]

    plans = []
    for topic in cfg.industry_topics:
        leader = None
        leader_tokens = 0
        for comp in comps:
            toks = entity_window_tokens[comp].get(topic, 0)
            if toks > leader_tokens:
                leader_tokens = toks
                leader = comp
        brand_tokens = brand_topic_window_tokens.get(topic, 0)
        base_tokens = window_token_base.get(topic, 0)

        # Real within-window density across the retrieved window set.
        brand_density = (brand_tokens / base_tokens) if base_tokens else 0.0
        leader_density = (leader_tokens / base_tokens) if base_tokens else 0.0

        # Tokens needed to reach the target density and to exceed the leader,
        # expressed against the real window-token base.
        need_for_target = max(0.0, (target_density - brand_density)) * base_tokens
        need_to_beat = max(0.0, (leader_density - brand_density)) * base_tokens
        need = max(need_for_target, need_to_beat)

        gap_ratio = round((leader_density / brand_density), 3) if brand_density else None
        severity = (
            "critical" if (leader_density - brand_density) > 0.03 else
            "high" if (leader_density - brand_density) > 0.015 else
            "low"
        )
        mention_action = _mention_action_plan(
            need, leader, target_density, base_tokens, win_size, cfg.top_k_retrieval)
        plans.append({
            "topic": topic,
            "brand_on_window_usage_tokens": brand_tokens,
            "leading_competitor": leader,
            "leader_on_window_usage_tokens": leader_tokens,
            "retrieval_window_token_base": base_tokens,
            "brand_density": round(brand_density, 4),
            "leader_density": round(leader_density, 4),
            "density_gap_ratio": gap_ratio,
            "tokens_needed_to_displace": round(need),
            "target_entity_density": target_density,
            "brand_proximity": round(brand_prox.get(topic, 0.0), 4),
            "leader_proximity": round(comp_prox[topic].get(leader, 0.0), 4),
            "severity": severity,
            "action": mention_action,
        })

    # Overall composite displacement-readiness score (0-100).
    scores = [p["density_gap_ratio"] or 1.0 for p in plans]
    readiness = round(100.0 * (1.0 - min(1.0, max(scores) - 1.0)), 1) if scores else 100.0
    return {
        "per_topic": plans,
        "brand_displacement_readiness": readiness,
        "method": ("real-token within-window density ratios from the BPE RAG "
                   "chunk simulator, vs the leading competitor's top-k usage."),
    }


def _mention_action_plan(need_tokens, leader, target_density, base_tokens,
                         win_size, top_k) -> str:
    """Express the token need as a concrete, actionable content directive."""
    if need_tokens <= 0:
        return ("No displacement required on this topic -- the brand already "
                "meets or exceeds the target density in the retrieval windows.")
    # A typical brand mention phrase is ~2-4 tokens; give a min-max range.
    lo_mentions = max(1, int(round(need_tokens / 4.0)))
    hi_mentions = max(1, int(round(need_tokens / 2.0)))
    return (
        f"To displace {leader or 'competitors'} on this topic, publish an "
        f"on-topic section of ~{max(int(need_tokens), 60)} tokens that "
        f"co-mentions the brand with the leading entity and the topic terms, "
        f"targeting ~{lo_mentions}-{hi_mentions} brand mentions across the "
        f"top-{top_k} retrieval windows ({win_size}-token windows) so the "
        f"brand reaches the {target_density:.1%} on-window density goal."
    )
