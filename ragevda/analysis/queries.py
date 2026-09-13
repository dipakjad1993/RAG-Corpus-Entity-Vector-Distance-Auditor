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
  * a natural question-frame *surface* (how/what/why/best/compare) -- but the
    substantive content always comes from real corpus terms, never from a
    hard-coded list of answer-bank tokens.

The output is a ranked list of synthetic queries per entity, each tagged with
the question type and the topic it maps to. Optionally an Ollama local LLM can
refine them into fluent, intent-mixed prompts (graceful fallback to the
corpus-derived templates).
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from typing import Dict, List

from ..utils import get_logger

logger = get_logger("ragevda.analysis.queries")

# Question frames by intent surface. ``{topic}`` and ``{brand}`` are the only
# injected slots -- every other term in a generated query comes from the real
# corpus (entities, window phrases, competitor names).
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

# A tiny syntactic filter so a "topic" string can never inject leading
# question-mark fragments into a query.
_WORD_RE = re.compile(r"[^\w\s&-]")


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


def _corpus_phrases_for(ctx, entity: str, topic: str, k: int = 6) -> List[str]:
    """Extract real, distinctive n-gram phrases from the windows that mention
    the entity AND are relevant to the topic.

    This is what makes the synthetic queries *grounded* rather than templated:
    the retrieved chunks themselves contribute their own salient phrases, so an
    operator can see what real content is being surfaced for that entity.
    """
    phrases: List[str] = []
    if not ctx:
        return phrases
    # Collect the sentences from documents that are relevant to the topic and
    # that mention the entity (via the real mention patterns).
    from ..nlp.ner import NER
    focus = ctx.config.all_entities()
    patterns, alias_to_entity = NER.build_mention_patterns(
        focus, ctx.config.entity_alias_map())
    for doc in ctx.docs:
        per = ctx.doc_topic_max_sim.get(doc.doc_id, {})
        sim = per.get(topic, 0.0)
        if sim <= 0:
            continue
        counts = NER.find_mentions(doc.text, patterns, alias_to_entity)
        if counts.get(entity, 0) <= 0:
            continue
        # take the sentences that contain the entity
        for sent in re.split(r"(?<=[.!?])\s+", doc.text):
            if not sent or len(sent) < 12:
                continue
            for key, pat in patterns.items():
                if alias_to_entity.get(key) == entity and pat.search(sent):
                    phrases.append(sent.strip())
                    break
        if len(phrases) >= k:
            break
    # de-duplicate while preserving order
    seen, uniq = set(), []
    for p in phrases:
        lp = p.lower()
        if lp not in seen:
            seen.add(lp)
            uniq.append(p)
    return uniq[:k]


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


def _clean_topic(topic: str) -> str:
    """Strip any stray punctuation so a topic can never produce a malformed
    question fragment when interpolated into a frame."""
    return _WORD_RE.sub("", topic).strip() or "this topic"


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
            clean = _clean_topic(topic)
            stats = ctx.entity_stats.get(ent)
            prox = stats.topic_proximity.get(topic, 0.0) if stats \
                and hasattr(stats, "topic_proximity") else 0.0
            # Real corpus phrases grounded in this entity's own retrieved
            # content (used to enrich / extend the generated query set).
            corpus_phrases = _corpus_phrases_for(ctx, ent, topic, k=2)
            for frame in frames[:4]:
                q = frame.format(topic=clean, brand=cfg.target_brand).strip()
                if not q or q.lower() in seen:
                    continue
                seen.add(q.lower())
                score = 0.5 + prox
                queries.append({
                    "query": q,
                    "corpus_evidence_phrases": corpus_phrases,
                    "topic": topic,
                    "type": ("informational" if "what" in q.lower() or "how" in q.lower()
                             else ("transactional" if "best" in q.lower() or "top" in q.lower()
                                   else "comparison")),
                    "retrieval_confidence": round(min(1.0, 0.3 + score), 3),
                })
        queries.sort(key=lambda x: x["retrieval_confidence"], reverse=True)
        out[ent] = queries[:limit]

    return {
        "per_entity": out,
        "verified": False,
        "estimate": True,
        "live_observed": False,
        "note": ("SYNTHETIC ESTIMATE — plausible retrieval prompts for the entity's "
                 "dominant topics (derived from real proximity + window "
                 "topics). Corpus-evidence phrases are verbatim sentence "
                 "fragments from the entity's own retrieved documents. NEVER "
                 "present as observed live search queries or engine telemetry."),
    }
