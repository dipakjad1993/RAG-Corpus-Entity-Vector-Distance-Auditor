"""Synthetic Query Generator (Reverse-Engineering RAG).

If your own content -- or a competitor's -- is being retrieved, the chain of
evidence is the set of queries a retriever would issue to surface those exact
chunks.  This module reverse-engineers the most plausible retrieval prompts for
each entity's retrieved windows, so a team can:

  * see *which questions* an AI engine is likely answering with a competitor's
    chunk but not yours;
  * use those queries as content / FAQ targets to win the same retrieval.

For each entity we combine:
  * the topic phrases it is most bound to (from the real proximity matrix),
  * the dominant topics of the windows it actually appears in,
  * a set of natural question frames (how/what/why/best/compare).

The output is a ranked list of synthetic queries per entity, each tagged with
the question type and the topic it maps to. Optionally an Ollama local LLM can
refine them into fluent, intent-mixed prompts (graceful fallback to templates).
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Dict, List

from ..utils import get_logger

logger = get_logger("ragevda.analysis.queries")

# Question frames by intent surface.
_FRAMES_INFORMATIONAL = [
    "What is {topic}?",
    "How does {topic} work?",
    "Why is {topic} important?",
    "What are the benefits of {topic}?",
]
_FRAMES_TRANSACTIONAL = [
    "Best {topic} software",
    "Top {topic} tools ranked",
    "Which {topic} platform should I choose?",
    "{topic} pricing comparison",
]
_FRAMES_COMPARISON = [
    "{brand} vs alternatives for {topic}",
    "Is {brand} the best for {topic}?",
    "{topic}: how does {brand} compare to the leader?",
]
_FRAMES_LOCAL = [
    "{topic} near me",
    "{topic} services in my area",
]


def _entity_topic_scores(ctx) -> Dict[str, List[str]]:
    """Rank topics an entity is most bound to, from real proximity."""
    scores: Dict[str, List[str]] = defaultdict(list)
    for e in ctx.config.all_entities():
        stats = ctx.entity_stats.get(e)
        if not stats:
            continue
        ordered = sorted(stats.topic_proximity.items(), key=lambda kv: kv[1], reverse=True)
        scores[e] = [t for t, _ in ordered]
    return scores


def _frames_for(ctx) -> Dict[str, List[str]]:
    intent = ctx.config.search_intent
    if intent == "transactional":
        base = _FRAMES_TRANSACTIONAL
    elif intent == "comparison":
        base = _FRAMES_COMPARISON
    elif intent == "local":
        base = _FRAMES_LOCAL
    else:
        base = _FRAMES_INFORMATIONAL
    # Always include a comparison surface since RAG queries are rarely pure.
    return base + _FRAMES_COMPARISON


def generate_synthetic(ctx, limit: int = 12) -> Dict:
    """Produce ranked synthetic retrieval queries per focus entity."""
    cfg = ctx.config
    frames = _frames_for(ctx)
    entity_topics = _entity_topic_scores(ctx)

    out: Dict[str, List[Dict]] = {}
    for ent in cfg.all_entities():
        topics = entity_topics.get(ent, cfg.industry_topics) or cfg.industry_topics
        queries: List[Dict] = []
        seen = set()
        for topic in topics[:4]:
            for frame in frames[:4]:
                q = frame.format(topic=topic, brand=cfg.target_brand).strip()
                if not q or q.lower() in seen:
                    continue
                seen.add(q.lower())
                stats = ctx.entity_stats.get(ent)
                prox = stats.topic_proximity.get(topic, 0.0) if stats \
                    and hasattr(stats, "topic_proximity") else 0.0
                score = 0.5 + prox
                queries.append({
                    "query": q,
                    "topic": topic,
                    "type": "informational" if "what" in q.lower() or "how" in q.lower()
                            else ("transactional" if "best" in q.lower() or "top" in q.lower()
                                  else "comparison"),
                    "retrieval_confidence": round(min(1.0, 0.3 + score), 3),
                })
        queries.sort(key=lambda x: x["retrieval_confidence"], reverse=True)
        out[ent] = queries[:limit]

    return {
        "per_entity": out,
        "note": ("Each query is a plausible retrieval prompt for the entity's "
                 "dominant topics (derived from real proximity + window topics)."),
    }
