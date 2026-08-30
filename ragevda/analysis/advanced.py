"""Consolidated advanced analyses (the enterprise feature set).

Runs the new analysis engines in one place so the orchestrator stays clean.
Produces one ``advanced`` dict consumed by reporting + the dashboard + the web
narrative page:

  * RAG chunking & contextual-window simulator    -> token windows / retrieval
  * Automated token-density adjuster              -> displacement targets
  * Sentiment / hallucination auditor             -> brand framing risk
  * Vector-poisoning / negative-SEO detector      -> spam co-citation risk
  * Engine-matrix Share of Voice heatmap          -> topic x AI-engine SoV
  * Synthetic query generator                     -> reverse-engineered prompts
  * Semantic-drift time-series DB + deltas        -> cross-run drift + alerts
  * Optional local-LLM gap analysis               -> free-text rationale
"""

from __future__ import annotations

import logging
from typing import Dict

from ..nlp.llm import LLMGapEngine, llm_gap_summary
from ..utils import get_logger
from . import chunking, drift, density, sentiment, poisoning, engine as engine_mod
from .queries import generate_synthetic

logger = get_logger("ragevda.analysis.advanced")


def run_advanced(ctx, config, proximity_rows, citation_result,
                 invisibility_result, job_id, generated_at) -> Dict:
    """Execute every new analysis engine and return the consolidated report."""
    result: Dict[str, Dict] = {}

    # 1. RAG chunking & contextual-window simulator
    windows_by_doc = chunking.build_chunk_windows(
        ctx.docs, ctx.topic_vecs, ctx.doc_topic_max_sim, config)
    chunking.mark_retrieved_windows(
        windows_by_doc, ctx.doc_topic_max_sim, config,
        topic_thresholds=getattr(ctx, "topic_thresholds", None))
    window_stats = _window_stats(windows_by_doc)
    result["chunking"] = {
        "windows_by_doc": None,           # too large for JSON; keep summaries
        "window_count": window_stats["count"],
        "retrieved_count": window_stats["retrieved"],
        "tokens_processed": window_stats["tokens"],
        "chunk_tokens": config.chunk_tokens,
        "chunk_overlap_tokens": config.chunk_overlap_tokens,
        "per_doc_windows": window_stats["per_doc"],
    }

    # 2. Automated token-density adjuster
    result["token_density"] = density.analyze_token_density(
        ctx, proximity_rows, windows_by_doc)

    # 3. Sentiment / hallucination auditor
    result["sentiment"] = sentiment.analyze_sentiment(
        ctx.docs, config, windows_by_doc)

    # 4. Vector-poisoning / negative-SEO detector
    result["poisoning"] = poisoning.analyze_poisoning(ctx.docs, config)

    # 5. Engine-matrix Share of Voice heatmap
    result["engine_matrix"] = engine_mod.analyze_engine_matrix(
        ctx, citation_result, invisibility_result)

    # 6. Synthetic query generator
    result["synthetic_queries"] = generate_synthetic(
        ctx, limit=config.synthetic_query_count)

    # 7. Semantic-drift time-series DB + deltas
    store = drift.DriftStore(config.drift_db_path())
    try:
        result["drift"] = drift.compute_drift(
            store, job_id, generated_at, config, proximity_rows,
            invisibility_result.get("per_topic", []))
    finally:
        store.close()

    # 8. Optional local-LLM gap analysis
    llm_engine = LLMGapEngine(config)
    try:
        result["llm"] = llm_gap_summary(
            llm_engine, ctx, result["token_density"], result["sentiment"])
    finally:
        llm_engine.close()

    return result


def _window_stats(windows_by_doc: Dict) -> Dict:
    count = 0
    retrieved = 0
    tokens = 0
    per_doc = {}
    for doc_id, wins in windows_by_doc.items():
        per_doc[str(doc_id)] = len(wins)
        count += len(wins)
        tokens += sum(w.tokens for w in wins)
        retrieved += sum(1 for w in wins if w.retrieved)
    return {"count": count, "retrieved": retrieved, "tokens": tokens,
            "per_doc": per_doc}
