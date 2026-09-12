"""Structured CSV / JSON reporting for data-pipeline integration."""

from __future__ import annotations

import csv
import json
import logging
import os
from typing import Any, Dict, List

from ..utils import get_logger

logger = get_logger("ragevda.reporting.csv_json")


def _ensure(dir_path: str) -> None:
    os.makedirs(dir_path, exist_ok=True)


def write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
    logger.info("wrote JSON report: %s", path)


def _write_csv(path: str, rows: List[Dict], columns: List[str]) -> None:
    if not rows:
        # still emit header-only file
        rows = [{}]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    logger.info("wrote CSV: %s", path)


def write_csvs(out_dir: str, data: Dict[str, Any]) -> Dict[str, str]:
    _ensure(out_dir)
    paths: Dict[str, str] = {}

    # proximity
    prox = data["proximity"]["rows"]
    p = os.path.join(out_dir, "proximity_scores.csv")
    _write_csv(p, [
        {"topic": r["topic"], "entity": r["entity"], "proximity": r["proximity"],
         "label": r["label"], "docs_highly_relevant": r["docs_highly_relevant"]}
        for r in prox
    ], ["topic", "entity", "proximity", "label", "docs_highly_relevant"])
    paths["proximity"] = p

    # entity citation summary
    ent = data["citation_gap"]["entity_summary"]
    p = os.path.join(out_dir, "entity_citation_summary.csv")
    _write_csv(p, ent, [
        "entity", "docs_total", "docs_mentioned", "docs_linked",
        "docs_unlinked", "docs_omitted", "mention_rate_pct",
        "link_rate_of_mentions_pct",
    ])
    paths["entity_citation_summary"] = p

    # off-page targets
    tgt = data["citation_gap"]["off_page_targets"]
    p = os.path.join(out_dir, "off_page_targets.csv")
    _write_csv(p, [
        {"url": t["url"], "title": t["title"], "source_type": t["source_type"],
         "top_topic": t["top_topic"], "topic_relevance": t["topic_relevance"],
         "competitors_present": ";".join(t["competitors_present"]),
         "competitor_links": ";".join(t["competitor_links"])}
        for t in tgt
    ], ["url", "title", "source_type", "top_topic", "topic_relevance",
        "competitors_present", "competitor_links"])
    paths["off_page_targets"] = p

    # recommendations
    recs = data["recommendations"]
    p = os.path.join(out_dir, "recommendations.csv")
    _write_csv(p, [
        {"rank": r.get("rank"), "priority": r.get("priority"),
         "category": r.get("category"), "title": r.get("title"),
         "rationale": r.get("rationale"), "action": r.get("action"),
         "url": r.get("url") or "", "score": r.get("score")}
        for r in recs
    ], ["rank", "priority", "category", "title", "rationale", "action",
        "url", "score"])
    paths["recommendations"] = p

    # invisibility per topic
    inv = data["invisibility"]["per_topic"]
    p = os.path.join(out_dir, "invisibility_per_topic.csv")
    _write_csv(p, inv, [
        "topic", "relevant_docs", "brand_present_docs",
        "competitor_present_docs", "vector_share_of_voice_pct",
        "topic_invisibility_pct",
    ])
    paths["invisibility_per_topic"] = p

    # data provenance / sources
    prov = data.get("provenance", [])
    p = os.path.join(out_dir, "sources.csv")
    _write_csv(p, prov, [
        "doc_id", "url", "title", "source_type", "domain",
        "top_topic", "top_topic_relevance", "chars", "threshold",
        "final_url", "http_status", "content_hash", "fetch_ms",
        "age_days", "staleness", "live", "content_type", "source_signal",
    ])
    paths["sources"] = p

    # data integrity / verification summary
    meta = data.get("meta", {})
    integ = meta.get("data_integrity", {})
    vrows = [{
        "verification_score": meta.get("verification_score", ""),
        "verified": meta.get("verified", ""),
        "models_real": integ.get("models_real", ""),
        "embedding_kind": integ.get("embedding_kind", ""),
        "embedding_model": integ.get("embedding_model", ""),
        "ner_kind": integ.get("ner_kind", ""),
        "ner_model": integ.get("ner_model", ""),
        "sentiment_model": integ.get("sentiment_model", ""),
        "harvest_ok": integ.get("harvest_ok", ""),
        "harvested_docs": integ.get("harvested_docs", ""),
        "dedup_removed": integ.get("dedup_removed", ""),
        "entities_with_mentions": integ.get("entities_with_mentions", ""),
        "entities_total": integ.get("entities_total", ""),
        "support_fraction": integ.get("support_fraction", ""),
        "provenance_complete": integ.get("provenance_complete", ""),
        "live_fraction": integ.get("live_fraction", ""),
        "fresh_pct": (integ.get("freshness_summary") or {}).get("fresh_pct", ""),
        "harvest_warning": meta.get("harvest_warning", ""),
    }]
    pv = os.path.join(out_dir, "verification.csv")
    _write_csv(pv, vrows, [
        "verification_score", "verified", "models_real", "embedding_kind",
        "embedding_model", "ner_kind", "ner_model", "sentiment_model",
        "harvest_ok", "harvested_docs", "dedup_removed",
        "entities_with_mentions", "entities_total", "support_fraction",
        "provenance_complete", "live_fraction", "fresh_pct", "harvest_warning",
    ])
    paths["verification"] = pv

    _write_advanced_csvs(out_dir, data, paths)
    return paths


def _write_advanced_csvs(out_dir: str, data: Dict[str, Any],
                         paths: Dict[str, str]) -> None:
    """Enterprise/advanced output CSVs (sentiment, engine SoV, density,
    poisoning, drift, RAG brief rows). The data is optional so older reports
    still render header-only files cleanly."""
    adv = data.get("advanced", {}) or {}

    # --- sentiment audit -------------------------------------------------
    sent = adv.get("sentiment", {}).get("per_entity", []) or []
    p = os.path.join(out_dir, "sentiment_audit.csv")
    _write_csv(p, sent, [
        "entity", "mentions", "positive_pct", "neutral_pct",
        "negative_pct", "net_sentiment", "risk_windows", "framing",
    ])
    paths["sentiment_audit"] = p

    # sentiment risk windows (verbatim negative-framed brand mentions)
    risks = adv.get("sentiment", {}).get("risk_windows", []) or []
    p = os.path.join(out_dir, "sentiment_risk_windows.csv")
    _write_csv(p, [
        {"entity": r.get("entity"), "url": r.get("url"), "title": r.get("title"),
         "polarity": r.get("polarity"), "snippet": r.get("snippet")}
        for r in risks
    ], ["entity", "url", "title", "polarity", "snippet"])
    paths["sentiment_risk_windows"] = p

    # --- engine-matrix SoV heatmap --------------------------------------
    eng = adv.get("engine_matrix", {}).get("cells", []) or []
    p = os.path.join(out_dir, "share_of_voice_heatmap.csv")
    _write_csv(p, eng, [
        "topic", "engine", "vector_sov_pct", "brand_presence_w",
        "competitor_presence_w", "relevant_docs", "confidence",
    ])
    paths["share_of_voice_heatmap"] = p

    # --- token-density adjuster -----------------------------------------
    dens = adv.get("token_density", {}).get("per_topic", []) or []
    p = os.path.join(out_dir, "token_density_adjuster.csv")
    _write_csv(p, dens, [
        "topic", "brand_on_window_usage_tokens", "leading_competitor",
        "leader_on_window_usage_tokens", "brand_density", "leader_density",
        "density_gap_ratio", "tokens_needed_to_displace",
        "target_entity_density", "brand_proximity", "leader_proximity",
        "severity", "action",
    ])
    paths["token_density_adjuster"] = p

    # --- vector-poisoning / negative SEO --------------------------------
    pois_sources = adv.get("poisoning", {}).get("sources", []) or []
    p = os.path.join(out_dir, "poisoning_sources.csv")
    _write_csv(p, [
        {"url": s.get("url"), "title": s.get("title"), "domain": s.get("domain"),
         "source_type": s.get("source_type"),
         "poisoning_risk": s.get("poisoning_risk"),
         "risk_factors": s.get("risk_factors"),
         "tokens": s.get("tokens"),
         "outbound_links": s.get("outbound_links"),
         "toxic_cluster_hits": s.get("toxic_cluster_hits"),
         "link_ratio": s.get("link_ratio"),
         "thin_score": s.get("thin_score"),
         "repetition_score": s.get("repetition_score"),
         "machine_score": s.get("machine_score"),
         "entities_co_cited": ";".join(s.get("entities_co_cited", []))}
        for s in pois_sources
    ], ["url", "title", "domain", "source_type", "poisoning_risk",
        "risk_factors", "tokens", "outbound_links", "toxic_cluster_hits",
        "link_ratio", "thin_score", "repetition_score", "machine_score",
        "entities_co_cited"])
    paths["poisoning_sources"] = p

    pois_exp = adv.get("poisoning", {}).get("entity_exposure", []) or []
    p = os.path.join(out_dir, "poisoning_exposure.csv")
    _write_csv(p, pois_exp, [
        "entity", "sources_co_cited", "toxic_sources",
        "toxic_share_pct", "flags",
    ])
    paths["poisoning_exposure"] = p

    # --- semantic drift --------------------------------------------------
    drifts = adv.get("drift", {}).get("per_topic", []) or []
    p = os.path.join(out_dir, "semantic_drift.csv")
    _write_csv(p, drifts, [
        "topic", "proximity", "invisibility_pct", "sov_pct",
        "proximity_delta", "invisibility_delta", "sov_delta",
        "has_prior", "prior_generated_at", "relevant_docs",
        "data_points", "trend_proximity_per_run", "trend_invisibility_per_run",
        "trend_sov_per_run", "anomaly", "anomaly_metric",
    ])
    paths["semantic_drift"] = p

    # --- source freshness / liveness ------------------------------------
    fresh = data.get("freshness", {}).get("per_source", []) or []
    p = os.path.join(out_dir, "source_freshness.csv")
    _write_csv(p, fresh, [
        "doc_id", "url", "domain", "http_status", "live", "fetch_latency_ms",
        "age_days", "staleness", "source_signal", "last_modified_raw",
        "server_date_raw", "content_type", "schema_structured_data",
    ])
    paths["source_freshness"] = p

    # --- synthetic queries ----------------------------------------------
    syn = adv.get("synthetic_queries", {}).get("per_entity", {}) or {}
    syn_rows = [
        {"entity": e, "query": q.get("query"), "topic": q.get("topic"),
         "type": q.get("type"), "retrieval_confidence": q.get("retrieval_confidence")}
        for e, qs in syn.items() for q in qs
    ]
    p = os.path.join(out_dir, "synthetic_retrieval_queries.csv")
    _write_csv(p, syn_rows, [
        "entity", "query", "topic", "type", "retrieval_confidence",
    ])
    paths["synthetic_retrieval_queries"] = p
