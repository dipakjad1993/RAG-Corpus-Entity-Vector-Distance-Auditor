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

import numpy as np

from .config import RunConfig
from .harvester.duckduckgo import DuckDuckGoHarvester
from .harvester.file_reader import FileHarvester
from .harvester.searxng import SearXNGHarvester
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

# Phase markers consumed by the web progress bar (webapp._PROGRESS_RULES).
# Every long phase logs start + end so the UI never looks stuck and the run
# always proceeds to the next phase instead of stalling silently.
def _phase(msg: str) -> None:
    logger.info("%s", msg)


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
    """Run the configured live harvester with enterprise fallback chain.

    Priority (2026): ``multi`` (SearXNG + Brave/Tavily/Exa fan-out) ->
    SearXNG (self-hosted) -> Brave/Tavily/Exa APIs -> DuckDuckGo HTML scrape
    (FALLBACK ONLY: fragile, legally grey, zero Reddit/YouTube depth) ->
    file corpus. Never returns an all-zero run silently.
    Returns ``(docs, stats, note)``.
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
        return _run_harvester(FileHarvester)

    if kind in ("multi", "answers"):
        # Paid-API fan-out first (Brave/Tavily/Exa), then SearXNG, then DDG.
        from .harvester.paid_search import multi_search
        from .harvester.base import new_document
        from .harvester.cleaner import extract_text
        paid = multi_search(queries[0] if queries else "", config, depth) if queries else []
        docs = []
        if paid:
            from .utils import HttpClient
            c = HttpClient(timeout=config.request_timeout,
                           user_agent=config.user_agent, proxy=config.proxy,
                           allowlist=getattr(config, "fetch_allowlist", None) or None)
            try:
                for url, title, snippet in paid[:depth]:
                    try:
                        from .harvester.base import robots_allowed
                        if not robots_allowed(url, config.user_agent):
                            continue
                        r = c.get(url)
                        if r.status_code != 200:
                            continue
                        try:
                            text = extract_text(r.text, url=url) or snippet
                        except Exception:  # noqa: BLE001
                            text = snippet
                        docs.append(new_document(url, title or url, "web",
                                                 queries[0] if queries else "",
                                                 text=text or snippet,
                                                 final_url=str(r.url),
                                                 http_status=r.status_code))
                    except Exception:  # noqa: BLE001
                        continue
            finally:
                c.close()
            if docs:
                return docs, {"paid_api_docs": len(docs)}, "primary: Brave/Tavily/Exa APIs"
        # fall through to searxng -> DDG when paid APIs yield nothing

    if kind in ("searxng", "multi", "answers"):
        reachable = _probe_searxng(config) if getattr(config, "searxng_base_url", "") else None
        if reachable:
            docs, stats, _ = _run_harvester(SearXNGHarvester)
            if docs:
                return docs, stats, None
            note = "SearXNG reachable but returned 0 documents; trying paid APIs then DDG fallback."
            logger.warning(note)
        elif getattr(config, "searxng_base_url", ""):
            note = "SearXNG unreachable; trying paid APIs then DDG fallback."
            logger.warning(note)

    # default: duckduckgo FALLBACK ONLY (kept for offline/zero-key boxes).
    logger.warning("DDG HTML scrape is FALLBACK-ONLY (fragile/TOS-grey, no UGC depth). "
                   "Configure SearXNG or BRAVE/TAVILY/EXA keys for primary coverage.")
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


def _shingles(text: str, k: int = 5) -> set:
    toks = [t for t in text.lower().split() if t]
    if len(toks) < k:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def _dedupe(docs: List, config) -> "tuple[List, int]":
    """Drop exact + near-duplicate harvested documents so metrics are not
    inflated by the same article served from multiple URLs. Returns the
    de-duplicated list and the number of documents removed.

    Exact duplicates: identical body text (sha1). Near duplicates: same domain
    AND same normalized title (syndicated mirrors) OR shingle-Jaccard >=
    ``near_dup_threshold`` (default 0.95) on body text.
    """
    if not config.dedupe_near:
        return docs, 0
    threshold = float(getattr(config, "near_dup_threshold", 0.95) or 0.95)
    seen_text: set = set()
    seen_title_domain: set = set()
    kept_shingles: List[set] = []
    uniq: List = []
    removed = 0
    for d in docs:
        body = (d.text or "").strip()
        text_h = hashlib.sha1(body.encode("utf-8", "ignore")).hexdigest()
        title_key = (d.domain or "").lower() + "|" + (d.title or "").strip().lower()
        if text_h in seen_text or title_key in seen_title_domain:
            removed += 1
            continue
        sh = _shingles(body)
        is_near = False
        if sh:
            for prev in kept_shingles:
                if not prev or not sh:
                    continue
                inter = len(sh & prev)
                union = len(sh | prev)
                jacc = inter / union if union else 0.0
                if jacc >= threshold:
                    is_near = True
                    break
        if is_near:
            removed += 1
            logger.info("near-duplicate dropped (jaccard>=%.2f): %s", threshold, d.url)
            continue
        seen_text.add(text_h)
        seen_title_domain.add(title_key)
        kept_shingles.append(sh)
        uniq.append(d)
    return uniq, removed


def run(config: RunConfig, docs: Optional[List] = None) -> Dict:
    """Execute the full audit. Returns the consolidated report dict."""
    try:
        config.apply_env_overrides()
    except Exception:  # noqa: BLE001
        pass
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
        _phase(f"harvest plan: {len(queries)} queries x depth {config.crawl_depth} "
               f"(max_pages={config.max_pages}, max_queries={config.max_search_queries})")
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
    _phase("augmenting corpus: feeds + UGC (reddit/youtube/tiktok) + answer harvester")
    import time as _t
    try:
        from .harvester.feeds import FeedHarvester
        augmenter = FeedHarvester(config)
        try:
            extra = augmenter.harvest(config.search_queries(), config.crawl_depth)
        finally:
            augmenter.close()
        # P0: first-class UGC (Reddit / YouTube / TikTok) — earned media is
        # 80-90% of AI answers; skipping it makes invisibility lie.
        # Time-boxed: UGC hits slow third parties (reddit/youtube/tiktok) that
        # can each stall for a full HTTP timeout. The whole UGC block gets a
        # bounded budget (default 90s, RAGEVDA_UGC_TIMEOUT) and a reduced query
        # set so a slow network can never freeze the audit mid-run.
        try:
            import os as _os
            _ugc_budget = float(_os.environ.get("RAGEVDA_UGC_TIMEOUT", "90") or 90)
            _ugc_t0 = _t.perf_counter()
            from .harvester.ugc import harvest_reddit, harvest_youtube, harvest_tiktok
            ugc_q = config.search_queries()[:5]
            _phase(f"UGC harvest: {len(ugc_q)} seed queries (budget {_ugc_budget:.0f}s)")
            ugc = harvest_reddit(ugc_q, config)
            if _t.perf_counter() - _ugc_t0 < _ugc_budget:
                ugc = ugc + harvest_youtube(ugc_q, config)
            else:
                logger.warning("UGC budget exhausted after reddit; skipping youtube/tiktok")
            if _t.perf_counter() - _ugc_t0 < _ugc_budget:
                ugc = ugc + harvest_tiktok(ugc_q, config)
            else:
                logger.warning("UGC budget exhausted; skipping tiktok")
            if ugc:
                extra = (extra or []) + ugc
                harvest_stats["ugc_docs"] = len(ugc)
                logger.info("UGC corpus: +%d reddit/youtube/tiktok doc(s)", len(ugc))
        except Exception as exc:  # noqa: BLE001
            logger.warning("UGC harvest skipped: %s", exc)
        # P0: Live LLM Answer Harvester (forward-track real prompts x personas).
        try:
            from .prompt_library import build_prompts
            from .harvester.answers import harvest_answers
            prompts = build_prompts(config)
            if prompts and getattr(config, "answer_harvester", "off") != "off":
                ans = harvest_answers(prompts, config)
                if ans:
                    extra = (extra or []) + ans
                    harvest_stats["answer_docs"] = len(ans)
        except Exception as exc:  # noqa: BLE001
            logger.warning("answer harvest skipped: %s", exc)
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
    _phase(f"dedupe corpus: {len(docs)} harvested doc(s)")
    docs, dedup_removed = _dedupe(docs, config)
    if dedup_removed:
        logger.info("removed %d duplicate document(s) from corpus", dedup_removed)
        harvest_stats["dedup_removed"] = dedup_removed
    logger.info("corpus size: %d documents", len(docs))
    _phase(f"corpus built: {len(docs)} documents (dedup removed {dedup_removed})")
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
    _phase("building analysis context: chunk + embed + NER graph")
    ctx = build_context(config, docs, embedder, ner, cooccur)

    # ---- 3. Analysis ------------------------------------------------
    _phase("proximity analysis: brand vs competitor vector distance")
    prox = analyze_proximity(ctx)
    _phase("citation-gap analysis: linked vs unlinked vs omitted")
    cit = analyze_citation_gap(ctx)
    _phase("invisibility analysis: per-topic RAG invisibility index")
    inv = analyze_invisibility(ctx, cit)
    _phase("generating recommendations: prioritized action list")
    recs = generate_recommendations(ctx, prox, cit, inv)
    _phase("advanced engines: chunking, density, sentiment, poisoning, "
           "engine-matrix, queries, drift, LLM, visibility, fanout")
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
            store.insert_chunk_embeddings(doc_id, np.stack(vecs, 0))
    for ent, stats in ctx.entity_stats.items():
        if stats.centroid is not None:
            store.insert_entity_centroid(ent, stats.centroid)
    store.close()

    # Data provenance: every harvested source behind the metrics, with the
    # real-fetch evidence (final URL, HTTP status, content hash, latency).
    _phase("freshness validation: liveness + age signals per source")
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
    _phase("persisting corpus to DuckDB + writing JSON report")
    json_path = os.path.join(out_dir, "report.json")
    write_json(json_path, report)
    _phase("generating CSV reports")
    csv_paths = write_csvs(out_dir, report)
    _phase("wrote HTML dashboard")
    html_path = os.path.join(out_dir, "dashboard.html")
    write_dashboard(html_path, report)
    write_rag_brief(os.path.join(out_dir, "rag_content_brief.md"), report)
    write_jsonld(os.path.join(out_dir, "schema_jsonld_patch.json"), report)
    # Consolidated enterprise outputs: llms.txt + agent.json + MCP manifest.
    try:
        from .reporting.llms import write_llms_outputs
        write_llms_outputs(out_dir, report, config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("llms.txt/MCP outputs skipped: %s", exc)
    # Closed-loop execution bundle: action_plan + wp_drafts.
    try:
        from .reporting.action_plan import write_action_plan
        write_action_plan(out_dir, report, config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("action_plan outputs skipped: %s", exc)
    # Looker Studio connector bundle (stdlib csv only — LITE-safe).
    try:
        from .reporting.looker import write_looker_bundle
        # visibility/funnel live under advanced only after run_advanced;
        # write best-effort (empty table when gates fail-open).
        write_looker_bundle(out_dir, report, config)
    except Exception as exc:  # noqa: BLE001
        logger.warning("looker bundle skipped: %s", exc)
    # Eval gates (RAGAS-style): fail-loud scores inside report["advanced"]["eval"].
    try:
        from .eval.gates import run_eval_gates
        report["advanced"]["eval"] = run_eval_gates(report, config)
        write_json(json_path, report)  # re-persist with eval attached
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval gates skipped: %s", exc)

    logger.info("audit complete. Outputs in %s", out_dir)
    return report


def run_from_file(config_path: str) -> Dict:
    cfg = RunConfig.load(config_path)
    return run(cfg)
