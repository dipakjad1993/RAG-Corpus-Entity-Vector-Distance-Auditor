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

    # 9. C-suite Visibility Score (Semrush-style, auditable) — needs
    # proximity/citation/invisibility already computed; build a minimal
    # interim report view. Fail-open: never aborts the audit.
    try:
        from .visibility import compute_visibility
        _interim = {"proximity": {"rows": proximity_rows},
                    "citation_gap": citation_result,
                    "invisibility": invisibility_result}
        result["visibility"] = compute_visibility(_interim, config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("visibility score skipped: %s", exc)
        result["visibility"] = {"table": [], "method": "skipped"}

    # 10. Query fan-out expansion + volume weighting (forward tracking).
    try:
        from .fanout import expand_prompts
        titles = [getattr(d, "title", "") or "" for d in (ctx.docs or [])]
        result["fanout"] = expand_prompts(
            list(config.industry_topics or []),
            list(getattr(config, "prompt_frames", ["informational"]) or ["informational"]),
            list(getattr(config, "personas", ["default"]) or ["default"]),
            volume=int(getattr(config, "prompt_volume", 5) or 5),
            harvested_titles=titles)
    except Exception as exc:  # noqa: BLE001
        logger.warning("fan-out expansion skipped: %s", exc)
        result["fanout"] = {"prompts": [], "count": 0}

    # 11. Citation-source funnel + fan-out decomposition + outreach.
    try:
        from .citation_funnel import citation_funnel
        _prov = [{"url": getattr(d, "url", ""), "title": getattr(d, "title", ""),
                  "top_topic": ""} for d in (ctx.docs or [])]
        result["citation_funnel"] = citation_funnel(
            {"provenance": _prov, "citation_gap": citation_result}, config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("citation funnel skipped: %s", exc)
        result["citation_funnel"] = {"funnel": []}

    # 12. Persona x platform sentiment matrix + word association.
    try:
        from .sentiment_matrix import sentiment_matrix
        result["sentiment_matrix"] = sentiment_matrix(
            ctx.docs, config, result.get("sentiment"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("sentiment matrix skipped: %s", exc)
        result["sentiment_matrix"] = {"matrix": {}}

    # 13. AI-crawler analytics (log path via env AI_CRAWLER_LOG).
    try:
        import os as _os
        from .crawler import analyze_crawler_logs
        result["crawler"] = analyze_crawler_logs(
            log_path=_os.environ.get("AI_CRAWLER_LOG", ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning("crawler analytics skipped: %s", exc)
        result["crawler"] = {"configured": False}

    # 14. GSC Generative-AI + GA4 attribution (wired; configured:false w/o creds).
    try:
        from ..attribution import gsc_attribution, ga4_attribution
        result["attribution_gsc"] = gsc_attribution(config)
        result["attribution_ga4"] = ga4_attribution(config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("attribution skipped: %s", exc)

    # 15. P0 GEO depth: passage citation stealer + fan-out coverage + E-E-A-T +
    # entity-gain + reddit topics + media checks + multilingual. All fail-open.
    try:
        from .citation_reverse import reverse_citations
        _answers = [d.text for d in (ctx.docs or [])
                    if getattr(d, "source_type", "") == "answer" and (getattr(d, "text", "") or "").strip()]
        from ..nlp import Embedder as _Emb
        try:
            result["citation_reverse"] = reverse_citations(_answers, ctx.docs, _Emb(ctx.embedding_model))
        except Exception:
            result["citation_reverse"] = {"steals": [], "method": "embedder unavailable"}
    except Exception as exc:  # noqa: BLE001
        result["citation_reverse"] = {"steals": [], "method": f"skipped: {exc}"}
    try:
        from .fanout_exec import fanout_coverage
        from ..prompt_library import build_prompts as _bp
        _prompts = [p.get("text", "") for p in (_bp(config) or []) if isinstance(p, dict) and p.get("text")] or \
            list(config.industry_topics or [])
        result["fanout_coverage"] = fanout_coverage(_prompts, ctx.docs, config)
    except Exception as exc:  # noqa: BLE001
        result["fanout_coverage"] = {"clusters": [], "method": f"skipped: {exc}"}
    try:
        from .eeat_gate import eeat_gate
        result["eeat"] = eeat_gate(ctx.docs)
    except Exception as exc:  # noqa: BLE001
        result["eeat"] = {"rows": [], "method": f"skipped: {exc}"}
    try:
        from .entity_gain import score_corpus
        _counts = {getattr(d, "doc_id", ""): len(getattr(d, "entities", []) or [])
                   for d in (ctx.docs or [])} if hasattr(ctx.docs[0] if ctx.docs else {}, "entities") else {}
        result["entity_gain"] = score_corpus(ctx.docs, _counts, getattr(config, "target_brand", ""))
    except Exception as exc:  # noqa: BLE001
        result["entity_gain"] = {"rows": [], "method": f"skipped: {exc}"}
    try:
        from .reddit_topics import reddit_topics
        _aurls = [getattr(d, "url", "") for d in (ctx.docs or []) if getattr(d, "source_type", "") == "answer"]
        result["reddit_topics"] = reddit_topics(ctx.docs, _aurls)
    except Exception as exc:  # noqa: BLE001
        result["reddit_topics"] = {"subreddits": [], "method": f"skipped: {exc}"}
    try:
        from .media_checks import media_checks
        result["media"] = media_checks(ctx.docs, list(config.industry_topics or []))
    except Exception as exc:  # noqa: BLE001
        result["media"] = {"rows": [], "method": f"skipped: {exc}"}
    try:
        from ..nlp.multilingual import multilingual_report
        result["multilingual"] = multilingual_report(ctx.docs, config)
    except Exception as exc:  # noqa: BLE001
        result["multilingual"] = {"lang_counts": {}, "method": f"skipped: {exc}"}
    try:
        from ..reporting.white_label import white_label_header, mcp_tools_status
        result["white_label"] = white_label_header(config)
        result["mcp_tools"] = mcp_tools_status(config, ctx.docs)
    except Exception as exc:  # noqa: BLE001
        result["white_label"] = {"method": f"skipped: {exc}"}
    # 16. Synthetic queries are LEGACY (forward-tracked prompt library is
    # default since 2026); keep for back-compat, label clearly.
    if isinstance(result.get("synthetic_queries"), dict):
        result["synthetic_queries"]["legacy"] = True
        result["synthetic_queries"]["note"] = ("LEGACY: use advanced.fanout + "
            "prompt library forward tracking; synthetic kept for back-compat only.")

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
