"""End-to-end pipeline orchestrator.

Runs the four micro-engines in order:

1. Harvest  (Feature A)
2. Embed + NER + Co-occurrence (Features B & C)
3. Proximity / Citation gap / Invisibility / Recommendations (Feature D & metrics)
4. Persist to DuckDB + emit CSV / JSON / HTML reports

The function :func:`run` is the single integration point used by the CLI.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from dataclasses import replace as dc_replace
from typing import Dict, List, Optional

from .config import RunConfig
from .nlp import Embedder, NER, CoOccurrenceGraph
from .analysis import (
    build_context, analyze_proximity, analyze_citation_gap,
    analyze_invisibility, generate_recommendations, run_advanced,
)
from .storage import CorpusStore
from .reporting import (
    write_json, write_csvs, write_dashboard,
    write_rag_brief, write_jsonld,
)
from . import __version__
from .utils import get_logger

logger = get_logger("ragevda.orchestrator")


def _probe_searxng(config) -> Optional[str]:
    """Return the resolved SearXNG base URL if it is reachable, else None.

    A fast, single-request connectivity probe happens *before* the query loop
    so an unreachable/offline SearXNG instance does not burn N queries (each of
    which retries and logs a ``getaddrinfo``/connection failure).  Returning
    None signals the caller to fall back to DuckDuckGo.
    """
    if getattr(config, "harvester", "duckduckgo") != "searxng":
        return None
    base = (config.searxng_base_url or "").rstrip("/")
    if not base:
        return None
    from .harvester.searxng import SearXNGHarvester
    probe = SearXNGHarvester(config)
    try:
        ok = probe.ping()
        logger.info("SearXNG probe %s :: %s", "OK" if ok else "UNREACHABLE", base)
        return base if ok else None
    finally:
        probe.close()


def _harvest_or_fallback(config, queries, depth) -> tuple:
    """Run the configured (live) harvester, auto-falling back to DuckDuckGo.

    Never returns an all-zero run silently: if the primary SearXNG instance is
    unreachable, or reaches a reachable instance that yields nothing, we drop
    to DuckDuckGo (and, that failing, ``file``-mode corpus files/feeds).  Returns
    ``(docs, stats, note)`` where ``note`` describes the fallback path taken.
    """
    kind = getattr(config, "harvester", "duckduckgo")
    note: Optional[str] = None

    def _run_harvester(hcls) -> tuple:
        h = hcls(config)
        try:
            docs = h.harvest(queries, depth)
            return (docs or [], dict(h.stats), None)
        finally:
            h.close()

    if kind == "file":
        return _run_harvester(
            __import__("ragevda.harvester.file_reader", fromlist=["FileHarvester"]).FileHarvester
        )

    from .harvester.duckduckgo import DuckDuckGoHarvester

    if kind == "searxng":
        reachable = _probe_searxng(config)
        if not reachable:
            note = (
                "SearXNG unreachable; fell back to DuckDuckGo. "
                "Check searxng_base_url connectivity."
            )
            logger.warning(note)
            docs, stats, _ = _run_harvester(DuckDuckGoHarvester)
            return docs, stats, note
        docs, stats, _ = _run_harvester(
            __import__("ragevda.harvester.searxng", fromlist=["SearXNGHarvester"]).SearXNGHarvester
        )
        # Reachable but yielded no pages -> still fall back rather than emit an
        # empty report based on a live-but-empty SERP.
        if not docs:
            note = "SearXNG reachable but returned 0 documents; fell back to DuckDuckGo."
            logger.warning(note)
            fallback_docs, fallback_stats, _ = _run_harvester(DuckDuckGoHarvester)
            for k, v in fallback_stats.items():
                stats[k] = stats.get(k, 0) + v
            return (docs + fallback_docs), stats, note
        return docs, stats, note

    # default: duckduckgo (or unknown -> duckduckgo)
    return _run_harvester(DuckDuckGoHarvester)


def _serialize_citations(citations) -> List[Dict]:
    return [
        {
            "doc_id": c.doc_id, "url": c.url, "title": c.title,
            "source_type": c.source_type,
            "linked": sorted(c.linked), "unlinked": sorted(c.unlinked),
            "omitted": sorted(c.omitted),
            "max_topic": c.max_topic, "max_topic_sim": round(c.max_topic_sim, 4),
        }
        for c in citations
    ]


def _serialize_recs(recs) -> List[Dict]:
    return [
        {
            "rank": r.rank, "priority": r.priority, "category": r.category,
            "title": r.title, "rationale": r.rationale, "action": r.action,
            "url": r.url, "score": r.score,
        }
        for r in recs
    ]


def _dedupe(docs: List, config) -> "tuple[List, int]":
    """Drop exact + near-duplicate harvested documents so metrics are not
    inflated by the same article served from multiple URLs. Returns the
    de-duplicated list and the number of documents removed.

    Exact duplicates: identical body text (sha1). Near duplicates: same domain
    AND same normalized title (covers syndicated/mirrored pages).
    """
    if not config.dedupe_near:
        return docs, 0
    seen_text: set = set()
    seen_title_domain: set = set()
    uniq: List = []
    removed = 0
    for d in docs:
        text_h = hashlib.sha1(d.text.strip().encode("utf-8", "ignore")).hexdigest()
        title_key = (d.domain or "").lower() + "|" + d.title.strip().lower()
        if text_h in seen_text or title_key in seen_title_domain:
            removed += 1
            continue
        seen_text.add(text_h)
        seen_title_domain.add(title_key)
        uniq.append(d)
    return uniq, removed


def run(config: RunConfig, docs: Optional[List] = None) -> Dict:
    """Execute the full audit. Returns the consolidated report dict."""
    logger.info("RAG-EVDA v%s starting audit for brand '%s'",
                __version__, config.target_brand)
    import uuid
    job_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    ctx_job_id = job_id

    # ---- 1. Harvest --------------------------------------------------
    harvest_warning = None
    harvest_stats: Dict[str, int] = {}
    if docs is None:
        queries = config.search_queries()
        docs, harvest_stats, fallback_note = _harvest_or_fallback(
            config, queries, config.crawl_depth
        )
        # Backup path: if the live search yielded nothing (common with
        # aggressive rate-limiting or an offline box), retry once with
        # relaxed settings before giving up — the tool must never silently
        # emit an all-zero report.
        if not docs:
            logger.warning(
                "primary harvest returned 0 docs; retrying with relaxed "
                "settings (reddit/news off)"
            )
            relaxed = dc_replace(
                config, include_reddit=False, include_news=False
            )
            try:
                relaxed_docs, relaxed_stats, _note = _harvest_or_fallback(
                    relaxed, relaxed.search_queries(), relaxed.crawl_depth
                )
                docs = docs + relaxed_docs
                for k, v in relaxed_stats.items():
                    harvest_stats[k] = harvest_stats.get(k, 0) + v
            except Exception as exc:  # noqa: BLE001
                logger.warning("relaxed fallback harvest failed: %s", exc)
        if fallback_note and not harvest_warning:
            harvest_warning = fallback_note
    # ---- 1c. Augment with direct inputs (feeds / footprints / GPT) -----
    # Content feeds (RSS/sitemap), search-engine scraping footprints and local
    # ground-truth corpora are ingested directly, independent of the primary
    # search harvester, so the corpus always reflects these explicit inputs.
    if docs is None:
        docs = []
    try:
        from .harvester.feeds import FeedHarvester
        augmenter = FeedHarvester(config)
        try:
            extra = augmenter.harvest(config.search_queries(), config.crawl_depth)
        finally:
            augmenter.close()
        # Ground-truth corpora (own brand / whitepaper docs) via local files,
        # unless the primary harvester is already "file" (which ingests them).
        if config.harvester != "file" and (config.corpus_files or config.corpus_dir):
            try:
                from .harvester.file_reader import FileHarvester
                gh = FileHarvester(config)
                extra = extra + gh.harvest([], config.crawl_depth)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ground-truth corpus ingest failed: %s", exc)
        if extra:
            for k, v in augmenter.stats.items():
                harvest_stats[k] = harvest_stats.get(k, 0) + v
            docs = docs + extra
            logger.info("augmented corpus with %d direct-input document(s)", len(extra))
    except Exception as exc:  # noqa: BLE001
        logger.warning("direct-input augmentation skipped: %s", exc)
    # ---- 1b. De-duplicate harvested corpus -------------------------
    docs, dedup_removed = _dedupe(docs, config)
    if dedup_removed:
        logger.info("removed %d duplicate document(s) from corpus", dedup_removed)
        harvest_stats["dedup_removed"] = dedup_removed
    logger.info("corpus size: %d documents", len(docs))
    if not docs:
        harvest_warning = (
            "No documents could be harvested from live search. The analysis "
            "below reflects an EMPTY corpus — verify your internet connection "
            "and that DuckDuckGo is reachable, or supply a local corpus folder."
        )
        logger.warning("no documents harvested; producing empty report")

    # ---- 2. NLP engines --------------------------------------------
    # require_real_models (default True) makes the audit FAIL rather than emit
    # silently-degraded TF-IDF/regex numbers -- this is the core guarantee that
    # every persisted report is built on real local ML, not a cheap stand-in.
    embedder = Embedder(config.embedding_model, require_real=config.require_real_models)
    ner = NER(config.spacy_model, require_real=config.require_real_models)
    cooccur = CoOccurrenceGraph()
    ctx = build_context(config, docs, embedder, ner, cooccur)

    # ---- 3. Analysis ------------------------------------------------
    prox = analyze_proximity(ctx)
    cit = analyze_citation_gap(ctx)
    inv = analyze_invisibility(ctx, cit)
    recs = generate_recommendations(ctx, prox, cit, inv)
    advanced = run_advanced(
        ctx, config, prox["rows"], cit, inv,
        job_id=ctx_job_id,
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    )

    # ---- 4. Persist + report ---------------------------------------
    out_dir = config.output_dir
    import os
    os.makedirs(out_dir, exist_ok=True)
    db_path = os.path.join(out_dir, "corpus.duckdb")
    store = CorpusStore(db_path)
    for d in docs:
        store.insert_document(d)
    for doc_id, vecs in ctx.doc_chunk_vecs.items():
        if vecs:
            store.insert_chunk_embeddings(doc_id, __import__("numpy").stack(vecs, 0))
    for ent, stats in ctx.entity_stats.items():
        if stats.centroid is not None:
            store.insert_entity_centroid(ent, stats.centroid)
    store.close()

    # Data provenance: every harvested source behind the metrics, with the
    # real-fetch evidence (final URL, HTTP status, content hash, latency).
    from .analysis.freshness import validate_freshness
    freshness = validate_freshness(ctx.docs)
    freshness_by_id = {f["doc_id"]: f for f in freshness.get("per_source", [])}
    provenance = []
    for doc in ctx.docs:
        per = ctx.doc_topic_max_sim.get(doc.doc_id, {})
        best_topic = max(per, key=per.get) if per else ""
        best_sim = per.get(best_topic, 0.0)
        fr = freshness_by_id.get(doc.doc_id, {})
        provenance.append({
            "doc_id": doc.doc_id,
            "url": doc.url,
            "title": doc.title,
            "source_type": doc.source_type,
            "domain": doc.domain,
            "top_topic": best_topic,
            "top_topic_relevance": round(best_sim, 4),
            "chars": len(doc.text),
            "threshold": ctx.topic_thresholds.get(best_topic, config.high_relevance_threshold),
            "final_url": doc.final_url,
            "http_status": doc.http_status,
            "content_hash": doc.content_hash,
            "fetch_ms": doc.fetch_ms,
            "age_days": fr.get("age_days"),
            "staleness": fr.get("staleness"),
            "live": fr.get("live"),
            "content_type": fr.get("content_type", ""),
            "source_signal": fr.get("source_signal", ""),
        })

    # ---- Data integrity / verification -----------------------------
    # A transparent, reproducible score (0-100) for how much to trust THIS run.
    # The score is a weighted composite of independent, auditable signals:
    #   38 pts: real ML models loaded (sentence-transformers + spaCy)
    #   28 pts: harvest succeeded (non-empty, no empty-corpus warning)
    #   18 pts: share of target entities actually present in the corpus
    #    8 pts: every fetched doc has a recorded HTTP 200
    #    8 pts: live-source fraction (HTTP 2xx here and now) from freshness probe
    # Each component is exported separately below so a low score can be traced
    # to exactly which signal failed (never a black box).
    models_real = (ctx.embedding_kind == "sentence-transformers"
                   and ctx.ner_kind == "spacy")
    harvest_ok = bool(docs) and not harvest_warning
    focus = config.all_entities()
    supported = sum(1 for s in ctx.entity_stats.values() if s.total_mentions > 0)
    support_frac = (supported / len(focus)) if focus else 0.0
    prov_complete = all(
        (d.http_status == 200 and not str(getattr(d, "url", "")).startswith("file://"))
        or getattr(d, "source_type", "") == "file"
        for d in docs
    ) if docs else False
    # File-corpus runs are provenance-complete via hash+mtime, but must not
    # inflate the HTTP-live score — live_frac comes from freshness (file docs
    # are live=False there).
    # Freshness: share of sources that are LIVE (HTTP 2xx here and now).
    live_frac = (freshness.get("summary", {}).get("live_pct", 0.0) / 100.0) if docs else 0.0
    # Sub-scores, each on 0..1, audited independently.
    sub_scores = {
        "models_real_score": 1.0 if models_real else 0.0,
        "harvest_ok_score": 1.0 if harvest_ok else 0.0,
        "support_score": round(min(1.0, support_frac), 3),
        "provenance_score": 1.0 if prov_complete else 0.0,
        "live_score": round(live_frac, 3),
    }
    verification_score = round(
        38.0 * sub_scores["models_real_score"]
        + 28.0 * sub_scores["harvest_ok_score"]
        + 18.0 * sub_scores["support_score"]
        + 8.0 * sub_scores["provenance_score"]
        + 8.0 * sub_scores["live_score"], 1)
    verified = bool(models_real and harvest_ok and support_frac >= 0.5
                    and live_frac >= 0.9)
    data_integrity = {
        "models_real": models_real,
        "embedding_kind": ctx.embedding_kind,
        "embedding_model": ctx.embedding_model,
        "ner_kind": ctx.ner_kind,
        "ner_model": ctx.ner_model,
        "models_real_score": sub_scores["models_real_score"],
        "harvest_ok_score": sub_scores["harvest_ok_score"],
        "support_score": sub_scores["support_score"],
        "provenance_score": sub_scores["provenance_score"],
        "live_score": sub_scores["live_score"],
        "harvest_ok": harvest_ok,
        "harvested_docs": len(docs),
        "dedup_removed": dedup_removed,
        "entities_with_mentions": supported,
        "entities_total": len(focus),
        "support_fraction": round(support_frac, 3),
        "provenance_complete": prov_complete,
        "live_fraction": round(live_frac, 3),
        "freshness_summary": freshness.get("summary", {}),
        "sentiment_model": ((advanced.get("sentiment") or {}).get("model") or ""),
        "verification_score": verification_score,
        "verified": verified,
    }
    if not verified:
        logger.warning(
            "Run verification_score=%.1f (verified=%s). Sub-scores: models=%s "
            "harvest=%s support=%s provenance=%s live=%s -- treat outputs "
            "as LOW CONFIDENCE and inspect the failing sub-score(s).",
            verification_score, verified,
            sub_scores["models_real_score"], sub_scores["harvest_ok_score"],
            sub_scores["support_score"], sub_scores["provenance_score"],
            sub_scores["live_score"])

    report = {
        "meta": {
            "tool": "RAG-EVDA",
            "version": __version__,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "config": config.to_dict(),
            "embedding_kind": ctx.embedding_kind,
            "embedding_model": ctx.embedding_model,
            "ner_kind": ctx.ner_kind,
            "ner_model": ctx.ner_model,
            "context_stats": {
                "doc_count": len(docs),
                "graph": cooccur.stats(),
            },
            "topic_thresholds": ctx.topic_thresholds,
            "harvest_warning": harvest_warning,
            "harvest_stats": harvest_stats,
            "data_integrity": data_integrity,
            "verification_score": verification_score,
            "verified": verified,
        },
        "proximity": prox,
        "citation_gap": {
            **{k: v for k, v in cit.items() if k != "citations"},
            "citations": _serialize_citations(cit["citations"]),
        },
        "invisibility": inv,
        "recommendations": _serialize_recs(recs),
        "provenance": provenance,
        "freshness": freshness,
        "advanced": advanced,
    }

    # ---- write outputs ---------------------------------------------
    json_path = os.path.join(out_dir, "report.json")
    write_json(json_path, report)
    csv_paths = write_csvs(out_dir, report)
    html_path = os.path.join(out_dir, "dashboard.html")
    write_dashboard(html_path, report)
    write_rag_brief(os.path.join(out_dir, "rag_content_brief.md"), report)
    write_jsonld(os.path.join(out_dir, "schema_jsonld_patch.json"), report)

    logger.info("audit complete. Outputs in %s", out_dir)
    return report


def run_from_file(config_path: str) -> Dict:
    cfg = RunConfig.load(config_path)
    return run(cfg)
