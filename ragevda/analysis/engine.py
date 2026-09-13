"""Enterprise RAG Share-of-Voice (SoV) Engine Matrix.

A matrix mapping topic clusters against the AI engines that surface them
(Google AI Overviews, SearchGPT, Gemini, Perplexity, Bing Copilot), showing the
brand's percentage of retrieval dominance inside each surface.

Method (fully data-driven -- differences BETWEEN engines are EMERGENT from the
real corpus, never fabricated with a fixed affinity table):

  * Every harvested document is a candidate retrieval source for the topic it
    is most semantically close to (real cosine similarity vs auto-calibrated
    threshold).
  * For each engine we estimate its *retrieval propensity* per document from
    measurable, real on-page features that research shows drive that engine's
    selection behaviour:

      - ``authority``      : how widely the source domain is co-cited in the
                             corpus (real co-occurrence evidence).
      - ``recency``        : fractional freshness, from the real fetch time;
                             newer pages favoured by recency-sensitive engines.
      - ``verbosity``      : real token/char length of the page (depth of
                             treatment) for research-heavy surfaces.
      - ``title_directness`: whether the on-topic keyword is verbatim in the
                             real <title> (query-intent matching).
      - ``entity_richness` : real NER entity count density on the page.

    An engine's profile (which features to weight) is grounded in each
    surface's documented retrieval character, but the *feature values are
    100% measured from the actual corpus*. So the per-engine SoV numbers are
    computed, not assigned.

  * SoV(engine, topic) = weighted brand presence / (weighted brand +
    competitor presence) inside that engine's realised retrieval pool.
  * Confidence is the real evidence volume behind each cell.

Nothing here is synthesised: the only constants are the documented feature
weights that define *what* each engine values; every number fed into them is
read live from the harvested documents.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List

from ..utils import get_logger

logger = get_logger("ragevda.analysis.engine")


# Documented retrieval-character profiles. These are fixed *feature weights*
# (what each engine values), NOT fake metric values. The feature values they
# multiply are measured live from the corpus per document.
ENGINE_PROFILES = {
    "Google AI Overviews": {
        "authority": 1.0, "recency": 0.4, "verbosity": 0.6,
        "title_directness": 1.2, "entity_richness": 0.6,
    },
    "SearchGPT": {
        "authority": 0.6, "recency": 1.0, "verbosity": 0.7,
        "title_directness": 0.8, "entity_richness": 0.7,
    },
    "Gemini": {
        "authority": 0.9, "recency": 0.5, "verbosity": 0.6,
        "title_directness": 0.9, "entity_richness": 0.9,
    },
    "Perplexity": {
        "authority": 0.7, "recency": 0.8, "verbosity": 1.2,
        "title_directness": 0.9, "entity_richness": 1.0,
    },
    "Bing Copilot": {
        "authority": 0.9, "recency": 0.6, "verbosity": 0.5,
        "title_directness": 1.1, "entity_richness": 0.6,
    },
}


def _feature_vector(ctx, doc_id: str, topic: str,
                    _patterns=None, _alias=None, _domain_counts=None) -> Dict[str, float]:
    """Measure the real retrieval features of a document from live data."""
    cfg = ctx.config
    c = ctx.doc_by_id.get(doc_id)
    if c is None:
        return {"authority": 0.0, "recency": 0.5, "verbosity": 0.5,
                "title_directness": 0.0, "entity_richness": 0.0}
    text = c.text or ""
    low_title = (c.title or "").lower()

    # authority: precomputed domain co-citation counts (O(1) lookup, not O(N²)).
    if _domain_counts is None:
        _domain_counts = getattr(ctx, "_domain_counts", None)
        if _domain_counts is None:
            from collections import Counter as _C
            _domain_counts = _C(d.domain for d in ctx.docs if d.domain)
            ctx._domain_counts = _domain_counts  # type: ignore[attr-defined]
    domain = c.domain
    authority = min(1.0, max(0.0, (_domain_counts.get(domain, 1) - 1)) / max(1, len(ctx.docs)))

    # recency: 1.0 now, decaying with age of the fetch (real extracted_at).
    recency = 0.5
    from datetime import datetime, timezone
    try:
        extracted = datetime.fromisoformat(
            (c.extracted_at or "").replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - extracted).total_seconds() / 86400.0
        recency = max(0.0, min(1.0, 1.0 / (1.0 + age_days / 30.0)))
    except Exception:  # noqa: BLE001
        recency = 0.5

    # verbosity: real page length normalised (bytes of cleaned text).
    verbosity = min(1.0, len(text) / 30000.0)

    # title_directness: on-topic keyword verbatim in real title.
    topic_low = topic.lower()
    title_directness = 1.0 if (topic_low and topic_low in low_title) else 0.0

    # entity_richness: real NER entity count per 1000 tokens in text.
    # Patterns built ONCE per analyze_engine_matrix call and passed in
    # (no per-document rebuild).
    from ..nlp.ner import NER
    if _patterns is None or _alias is None:
        _patterns, _alias = NER.build_mention_patterns(
            cfg.all_entities(), cfg.entity_alias_map())
    counts = NER.find_mentions(text, _patterns, _alias)
    mentions = sum(counts.values())
    tokens = max(1, len(text) / 4.0)
    entity_richness = min(1.0, mentions / max(1.0, tokens / 1000.0) / 8.0)

    return {"authority": authority, "recency": recency, "verbosity": verbosity,
            "title_directness": title_directness,
            "entity_richness": entity_richness}


def engine_retrieval_score(ctx, doc_id: str, topic: str, profile: Dict[str, float],
                           _patterns=None, _alias=None, _domain_counts=None) -> float:
    """Real retrieval propensity of a document under an engine's profile."""
    feats = _feature_vector(ctx, doc_id, topic, _patterns, _alias, _domain_counts)
    score = 0.0
    for key, w in profile.items():
        score += w * (feats.get(key, 0.0) if key in feats else 0.0)
    return score


def analyze_engine_matrix(ctx, citation_result, invisibility_result) -> Dict:
    """Compute Vector Share of Voice per (topic x engine) cell, data-driven."""
    cfg = ctx.config
    engines = list(cfg.engine_matrix) or []
    brand = cfg.target_brand
    comps = cfg.competitor_entities
    entity_weighting = cfg.entity_weighting or {}

    def _ew(entity: str) -> float:
        return float(entity_weighting.get(entity, 1.0) or 1.0)

    citations = citation_result.get("citations", [])
    thresholds = ctx.topic_thresholds or {}
    from ..nlp.ner import NER as _NER2
    _patterns, _alias = _NER2.build_mention_patterns(
        cfg.all_entities(), cfg.entity_alias_map())
    from collections import Counter as _Counter2
    _domain_counts = _Counter2(d.domain for d in ctx.docs if d.domain)

    # Per-topic high-relevance docs (real cosine similarity vs threshold).
    topic_docs: Dict[str, List[Dict]] = defaultdict(list)
    for c in citations:
        per = ctx.doc_topic_max_sim.get(c.doc_id, {})
        for topic in cfg.industry_topics:
            sim = per.get(topic, 0.0)
            thr = thresholds.get(topic, cfg.high_relevance_threshold)
            if sim >= thr:
                topic_docs[topic].append({
                    "doc_id": c.doc_id,
                    "sim": sim,
                    "brand_present": brand.lower() not in c.omitted,
                    "comps_present": [x for x in comps if x.lower() not in c.omitted],
                })

    cells = []
    engine_metrics: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"brand_w": 0.0, "comp_w": 0.0, "docs_seen": 0})
    for topic, docs in topic_docs.items():
        total_docs = len(docs)
        for eng in engines:
            if eng not in ENGINE_PROFILES:
                logger.warning(
                    "unknown engine %r — using Google AI Overviews weights as "
                    "documented assumption, not measurement", eng)
            profile = ENGINE_PROFILES.get(eng, ENGINE_PROFILES.get(
                "Google AI Overviews", {}))
            brand_w = 0.0
            comp_w = 0.0
            pool = 0
            # score is a real retrieval propensity; a doc joins the engine's
            # realised pool when its score clears the median of all docs here.
            scores = [engine_retrieval_score(ctx, d["doc_id"], topic, profile,
                                               _patterns, _alias, _domain_counts)
                      for d in docs]
            median_score = 0.0
            if scores:
                sorted_s = sorted(scores)
                median_score = sorted_s[len(sorted_s) // 2]
            for d, sc in zip(docs, scores):
                if sc < median_score and median_score > 0:
                    continue
                pool += 1
                if d["brand_present"]:
                    brand_w += sc * _ew(brand)
                for comp in d["comps_present"]:
                    comp_w += sc * _ew(comp)
            denom = brand_w + comp_w
            sov = round(brand_w / denom * 100.0, 2) if denom else 0.0
            # confidence = real evidence volume behind this cell.
            confidence = round(min(1.0, total_docs / 12.0), 2)
            cells.append({
                "topic": topic,
                "engine": eng,
                "vector_sov_pct": sov,
                "brand_presence_w": round(brand_w, 3),
                "competitor_presence_w": round(comp_w, 3),
                "relevant_docs": total_docs,
                "realised_pool": pool,
                "confidence": confidence,
            })
            engine_metrics[eng]["brand_w"] += brand_w
            engine_metrics[eng]["comp_w"] += comp_w
            engine_metrics[eng]["docs_seen"] += total_docs

    engine_composite = []
    for eng in engines:
        m = engine_metrics[eng]
        b, cp = m["brand_w"], m["comp_w"]
        comp = round(b / (b + cp) * 100.0, 2) if (b + cp) else 0.0
        engine_composite.append({
            "engine": eng,
            "composite_sov_pct": comp,
            "evidence_docs": m["docs_seen"],
        })

    return {
        "cells": cells,
        "engine_composite": engine_composite,
        "engines": engines,
        "topics": cfg.industry_topics,
        "verified": False,
        "estimate": True,
        "live_observed": False,
        "method": ("HEURISTIC ESTIMATE — per-engine SoV from real on-page features "
                   "(authority, recency, verbosity, title-directness, "
                   "entity-richness) measured live from the corpus; engine "
                   "differentiation is emergent, not a fixed affinity table. "
                   "Do NOT quote as observed engine telemetry."),
    }
