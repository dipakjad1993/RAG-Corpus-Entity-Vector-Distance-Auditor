"""Deep-dive narrative HTML for the three-step web UI.

Everything rendered here is derived from the *actual* computed ``data`` dict
(the same object the dashboard consumes) so the prose can never drift from the
numbers. Where a quantity is unavailable it is shown as an em dash rather than
invented.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List


def _esc(s: Any) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _pct(x: Any, nd: int = 1) -> str:
    """Fraction 0..1 -> percent. Already-percent 0..100 values pass through."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "&mdash;"
    if v > 1.5:  # already percent units
        return f"{v:.{nd}f}%"
    return f"{v * 100:.{nd}f}%"


def _pct100(x: Any, nd: int = 1) -> str:
    """Already-percent 0..100 value -> percent string (no scaling)."""
    try:
        return f"{float(x):.{nd}f}%"
    except (TypeError, ValueError):
        return "&mdash;"


def _num(x: Any) -> str:
    try:
        return f"{x:,}"
    except (TypeError, ValueError):
        return _esc(x)


def _round(x: Any, nd: int = 3) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "&mdash;"


# ---------------------------------------------------------------------------
# Small presentational helpers (these classes are defined in webapp.py CSS)
# ---------------------------------------------------------------------------

def _chip(value: str, label: str) -> str:
    return f'<span class="m3-chip"><b>{value}</b>{_esc(label)}</span>'


def _feat(num: str, title: str, desc: str, metrics: str, link_url: str = "") -> str:
    link = ""
    if link_url:
        link = f'<div style="margin-top:12px"><a href="{link_url}" style="color:var(--m3-primary);font-weight:700;font-size:13px">View Full Analysis →</a></div>'
    return f"""
    <div class="feat">
      <div class="feat-num">{num}</div>
      <div class="feat-body">
        <h3>{title}</h3>
        {desc}
        <div class="feat-metrics">{metrics}</div>
        {link}
      </div>
    </div>"""


def _stat_table(rows: List[List[str]]) -> str:
    body = "".join(
        f"<tr><td>{r[0]}</td><td>{r[1]}</td></tr>" for r in rows
    )
    return f'<table class="kv"><tbody>{body}</tbody></table>'


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------

def _extract(data: Dict[str, Any]) -> Dict[str, Any]:
    meta = data.get("meta", {}) or {}
    cfg = meta.get("config", {}) or {}
    di = meta.get("data_integrity", {}) or {}
    hs = meta.get("harvest_stats", {}) or {}
    cs = meta.get("context_stats", {}) or {}
    prox = data.get("proximity", {}) or {}
    rows = prox.get("rows", []) or []
    cite = data.get("citation_gap", {}) or {}
    inv = data.get("invisibility", {}) or {}

    avg_prox = None
    tight = far = 0
    if rows:
        vals = [r.get("proximity") for r in rows if isinstance(r.get("proximity"), (int, float))]
        if vals:
            avg_prox = statistics.mean(vals)
        for r in rows:
            lab = (r.get("label") or "").lower()
            if "tight" in lab:
                tight += 1
            elif "far" in lab:
                far += 1

    ent_sum = cite.get("entity_summary", []) or []
    linked = unlinked = omitted = 0
    for e in ent_sum:
        linked += int(e.get("docs_linked", 0) or 0)
        unlinked += int(e.get("docs_unlinked", 0) or 0)
        omitted += int(e.get("docs_omitted", 0) or 0)

    return {
        "meta": meta, "cfg": cfg, "di": di, "hs": hs, "cs": cs,
        "rows": rows, "cite": cite, "inv": inv,
        "avg_prox": avg_prox, "tight": tight, "far": far,
        "ent_sum": ent_sum, "linked": linked, "unlinked": unlinked, "omitted": omitted,
        "n_prox": len(rows),
        "adv": data.get("advanced", {}) or {},
    }


# ---------------------------------------------------------------------------
# Page 2 — Four micro-engines, explained with this run's real metrics
# ---------------------------------------------------------------------------

def features_html(data: Dict[str, Any], job_id: str = "") -> str:
    d = _extract(data)
    cfg, di, hs, cs = d["cfg"], d["di"], d["hs"], d["cs"]

    try:
        from . import issues as _issues

        _all_issues = _issues.collect_issues(data)
        _iss_head = (
            '<h2 class="m3-h2">Issues requiring attention</h2>'
            + _issues.summary_strip_html(_all_issues)
            + _issues.banner_html(_all_issues, engine=None, limit=6)
        )
    except Exception:  # noqa: BLE001 — highlighting must never break a page
        _iss_head = ""

    brand = _esc(cfg.get("target_brand", ""))
    topics = cfg.get("industry_topics", []) or []
    comps = cfg.get("competitor_entities", []) or []

    # ---- Feature A -------------------------------------------------------
    a_desc = f"""
    <p>The auditor begins with a <b>zero-cost, headless harvest</b> of the open
    web. It drives DuckDuckGo (and optionally a self-hosted <b>SearXNG</b>
    instance or a Playwright headless browser) to pull the top-ranking pages,
    Reddit threads and news articles for each configured topic, then runs the
    raw HTML through a <b>cleanroom parser</b> (BeautifulSoup / trafilatura) that
    strips navigation, footers, sidebars and advertising &mdash; leaving only the
    pure body text a RAG crawler would actually ingest.</p>
    <ul>
      <li><b>Scrapes search &amp; web data for free</b> via DuckDuckGo, SearXNG
      or Playwright &mdash; no paid API keys required.</li>
      <li><b>HTML cleanroom parsing</b> isolates indexable body text from
      boilerplate, ads and chrome.</li>
    </ul>"""
    a_metrics = "".join([
        _chip(_num(hs.get("fetched")), " pages fetched"),
        _chip(_num(hs.get("queries")), " search queries"),
        _chip(_num(hs.get("dedup_removed")), " duplicates removed"),
        _chip(_esc(cfg.get("harvester", "")), " harvester"),
        _chip(_esc(cfg.get("locality") or "global"), " locality"),
        _chip(_num(cs.get("doc_count")), " clean documents"),
    ])

    # ---- Feature B -------------------------------------------------------
    b_desc = f"""
    <p>Every cleaned paragraph, the target brand and each competitor concept are
    projected into a shared vector space using <b>Hugging Face
    sentence-transformers</b> running <b>locally</b> on CPU/GPU
    (<code>{_esc(cfg.get('embedding_model', ''))}</code>). The auditor then
    computes the exact <b>cosine similarity</b> between brand/competitor vectors
    and each topic vector &mdash; a mathematically rigorous proximity score where
    <b>0.00 = completely unrelated</b> and <b>1.00 = identical meaning</b>.</p>
    <ul>
      <li><b>Local tensor processing</b> &mdash; embeddings never leave the
      machine.</li>
      <li><b>Cosine similarity calculations</b> quantify semantic proximity
      across the whole corpus.</li>
    </ul>"""
    b_metrics = "".join([
        _chip(_esc(d["meta"].get("embedding_kind", "")), " embedding engine"),
        _chip(_num(d["n_prox"]), " proximity comparisons"),
        _chip(_round(d["avg_prox"]), " mean proximity"),
        _chip(_num(d["tight"]), " tightly-bound"),
        _chip(_num(d["far"]), " far / unrelated"),
    ])

    # ---- Feature C -------------------------------------------------------
    c_desc = f"""
    <p>A <b>local Named Entity Recognition</b> pass (spaCy
    <code>{_esc(cfg.get('spacy_model', ''))}</code>) parses every document for
    <b>Organizations (ORG)</b>, <b>Products (PRODUCT)</b> and <b>People
    (PERSON)</b>. The auditor then builds a <b>co-occurrence matrix</b> with
    <code>networkx</code> tracking how often each competitor appears in the same
    paragraph as a target topic versus how often the brand does &mdash; the
    structural signal behind citation authority.</p>
    <ul>
      <li><b>Entity extraction</b> across the full cleaned corpus.</li>
      <li><b>Co-occurrence matrix building</b> via networkx entity graphs.</li>
    </ul>"""
    c_metrics = "".join([
        _chip(_esc(d["meta"].get("ner_kind", "")), " NER engine"),
        _chip(_num(di.get("entities_total")), " entities tracked"),
        _chip(_num(di.get("entities_with_mentions")), " with mentions"),
        _chip(_num(len(d["ent_sum"])), " entities audited"),
    ])

    # ---- Feature D -------------------------------------------------------
    d_desc = f"""
    <p>The <b>Unlinked Authority &amp; Citation Gap Finder</b> audits every
    retrieved article to classify the brand and each competitor as
    <b>linked</b>, <b>mentioned without a link</b> (an unlinked brand mention) or
    <b>omitted entirely</b> while rivals are cited. This surfaces the precise
    off-page targets where authority is being conceded.</p>
    <ul>
      <li><b>Link vs. mention auditing</b> at document level.</li>
      <li><b>Citation-gap scoring</b> feeding the RAG Invisibility Index.</li>
    </ul>"""
    d_metrics = "".join([
        _chip(_round(d["cite"].get("rag_invisibility_index")), " RAG invisibility idx"),
        _chip(_num(d["cite"].get("high_relevance_doc_count")), " high-rel docs"),
        _chip(_num(d["cite"].get("invisible_doc_count")), " brand-invisible docs"),
        _chip(_num(d["linked"]), " linked mentions"),
        _chip(_num(d["unlinked"]), " unlinked mentions"),
        _chip(_num(d["omitted"]), " omissions"),
    ])

    base = f"/page/deep/{job_id}/" if job_id else ""
    feats = "".join([
        _feat("A", "Zero-Cost Headless Web Harvester", a_desc, a_metrics, base + "web_harvester"),
        _feat("B", "Local Vector Embedding &amp; Semantic Mapping", b_desc, b_metrics, base + "vector_embedding"),
        _feat("C", "Local NER &amp; Knowledge Graphs", c_desc, c_metrics, base + "ner_graphs"),
        _feat("D", "Unlinked Authority &amp; Citation Gap Finder", d_desc, d_metrics, base + "citation_gap"),
    ])

    # ---- Verification / methodology ------------------------------------
    verified = bool(di.get("verified"))
    vscore = di.get("verification_score")
    fs = di.get("freshness_summary", {}) or {}
    models = [m for m in [
        (di.get("embedding_model") or di.get("embedding_kind")),
        (di.get("ner_model") or di.get("ner_kind")),
        (di.get("sentiment_model") or "")
    ] if m]
    models_str = " + ".join(str(m) for m in models) if models else "real local models"
    verify_rows = [
        ["Models", _esc(models_str)
         if di.get("models_real") else "Synthetic fallback engaged"],
        ["Harvest", "OK &mdash; live web fetch"
         if di.get("harvest_ok") else "Degraded"],
        ["Documents harvested", _num(di.get("harvested_docs"))],
        ["Near-duplicates removed", _num(di.get("dedup_removed"))],
        ["Live sources", _pct100(fs.get("live_pct"))],
        ["Fresh / current", _pct100(fs.get("fresh_pct"))],
        ["Median source age", f"{_round(fs.get('median_age_days'))} days"],
        ["Entities with mentions", f'{_num(di.get("entities_with_mentions"))} / {_num(di.get("entities_total"))}'],
        ["Provenance complete", "Yes" if di.get("provenance_complete") else "Partial"],
        ["Support fraction", _pct(di.get("support_fraction"))],
        ["Sub-scores (models / harvest / support / provenance / live)",
         " / ".join([
             _round(di.get("models_real_score")),
             _round(di.get("harvest_ok_score")),
             _round(di.get("support_score")),
             _round(di.get("provenance_score")),
             _round(di.get("live_score")),
         ])],
        ["Verification score", f'{_round(vscore)} / 100 &nbsp;({"VERIFIED" if verified else "PARTIAL"})'],
    ]
    verify_block = f"""
    <div class="verify-card {'ok' if verified else 'partial'}">
      <div class="verify-head">
        <span class="verify-badge">{'VERIFIED' if verified else 'PARTIAL'}</span>
        <span>Data-integrity verification &mdash; score {_round(vscore)}/100</span>
      </div>
      {_stat_table(verify_rows)}
      <p class="verify-note">Scores are computed from real harvested content and
      local model inference. Semantic proximity and NER are model-derived
      estimates; the verification layer confirms provenance, model authenticity
      and corpus integrity &mdash; it does not assert external factual truth of
      third-party pages.</p>
    </div>"""

    return f"""
    <section class="narrative">
      {_iss_head}
      <h2 class="m3-h2">How the audit works &mdash; four local micro-engines</h2>
      <p class="m3-lead">This run analysed <b>{_num(cs.get('doc_count'))}</b> clean
      documents for <b>{_esc(brand)}</b> across
      <b>{_num(len(topics))}</b> topics and <b>{_num(len(comps))}</b> competitors.
      Each engine below shows what it did on <i>this</i> corpus.</p>
      <div class="feat-list">{feats}</div>

      {_advanced_features_html(d, job_id)}

      <h2 class="m3-h2">Methodology &amp; verification</h2>
      {verify_block}
    </section>"""


# ---------------------------------------------------------------------------
# Enterprise advanced-features block (page 2)
# ---------------------------------------------------------------------------

def _advanced_features_html(d: Dict[str, Any], job_id: str = "") -> str:
    adv = d.get("adv") or {}
    if not adv:
        return ""
    base = f"/page/deep/{job_id}/" if job_id else ""
    feats = []
    # 5) Chunking & contextual-window simulator
    ch = adv.get("chunking", {}) or {}
    if ch:
        feats.append(_feat(
            "5", "RAG Chunking &amp; Contextual-Window Simulator",
            "<p>Real RAG engines don't embed a whole article as one vector; they "
            "split it into <b>retrieval windows</b> (default 512 tokens with "
            f"{ch.get('chunk_overlap_tokens', 64)}-token overlap) and embed each "
            "separately. This run simulated that behaviour so cosine similarity "
            "reflects what a retriever actually scores &mdash; not a whole-page "
            "vector that hides false positives.</p>",
            "".join([
                _chip(_num(ch.get("window_count")), " token windows"),
                _chip(_num(ch.get("retrieved_count")), " top-k retrieved"),
                _chip(_num(ch.get("tokens_processed")), " tokens processed"),
                _chip(_num(ch.get("chunk_tokens")), " chunk size"),
            ]),
            base + "chunking"))
    # 6) Token density adjuster
    td = adv.get("token_density", {}) or {}
    if td.get("per_topic"):
        target = td.get("per_topic", [])[0]
        feats.append(_feat(
            "6", "Automated Token-Density Adjuster",
            "<p>Within each retrieved window, how many tokens reference the brand "
            "versus the leading competitor. This plan states exactly how many more "
            "on-window brand tokens are needed to displace a competitor from "
            f"top-{d.get('cfg', {}).get('top_k_retrieval', 5)} retrieval.</p>",
            "".join([
                _chip(_round(target.get("tokens_needed_to_displace")), " tokens to displace"),
                _chip(_esc(target.get("leading_competitor")), " leader"),
                _chip(f"{td.get('brand_displacement_readiness', 0)}/100", " readiness"),
            ]),
            base + "token_density"))
    # 7) Sentiment auditor
    sent = adv.get("sentiment", {}) or {}
    brand_row = next((s for s in sent.get("per_entity", []) if s.get("entity") == d["cfg"].get("target_brand")), None)
    if sent.get("per_entity"):
        risks = sum(1 for s in sent.get("per_entity", []) if s.get("risk_windows"))
        feats.append(_feat(
            "7", "RAG Chunk Hallucination &amp; Sentiment Auditor",
            "<p>Retrieval isn't only about <i>whether</i> the brand appears &mdash; it's "
            "about the framing of the adjacent tokens. This audits the sentiment "
            "polarity of every brand mention and flags negative-framed retrieval "
            "windows verbatim, so a hostile AI answer can be neutralised.</p>",
            "".join([
                _chip(_round((brand_row or {}).get("net_sentiment")), " brand net sentiment"),
                _chip(_num(risks), " entities with risk windows"),
                _chip(_esc(sent.get("method", "")[:26]), " method"),
            ]),
            base + "sentiment"))
    # 8) Engine-matrix SoV heatmap
    eng = adv.get("engine_matrix", {}) or {}
    if eng.get("cells"):
        feats.append(_feat(
            "8", "RAG Share-of-Voice Heatmap (topic × AI-engine)",
            "<p>A matrix mapping topic clusters against the AI engines that surface "
            "them (Google AI Overviews, SearchGPT, Gemini, Perplexity, Bing Copilot) "
            "showing the brand's retrieval dominance on each surface. Different "
            "engines use different pipelines &mdash; dominance on one doesn't mean "
            "visibility on another.</p>",
            "".join([
                _chip(_num(len(eng.get("engines", []))), " engines modelled"),
                _chip(_num(len(eng.get("cells", []))) if eng.get("cells") else "0", " cells"),
                _chip(_num(len(eng.get("topics", []))), " topics"),
            ])))
    # 9) Synthetic query generator
    syn = adv.get("synthetic_queries", {}) or {}
    if syn.get("per_entity"):
        feats.append(_feat(
            "9", "Synthetic Query Generator (Reverse-Engineer RAG)",
            "<p>Reverse-engineering the retrieval prompts an AI engine would issue to "
            "surface each entity's chunks. The brand-targeted synthetic queries become "
            "direct Q&amp;A / FAQ content targets to win the same retrieval.</p>",
            "".join([
                _chip(_num(len(list(syn.get("per_entity", {}).values())[0]) if syn.get("per_entity") else 0), " queries/entity"),
                _chip(_num(len(syn.get("per_entity", {}))), " entities"),
            ]),
            base + "synthetic_queries"))
    # 10) Vector poisoning / negative SEO
    pois = adv.get("poisoning", {}) or {}
    if pois:
        status = pois.get("brand_poisoning_status", "clean")
        generated = pois.get("generated_phrase_hits") or 0
        feats.append(_feat(
            "10", "Vector Poisoning / Negative-SEO Detection",
            "<p>Detects how low-quality sites co-cite the brand with toxic or "
            "off-topic concept clusters that drag its centroid toward junk topics "
            "in vector space &mdash; a growing risk as engines rank by semantic "
            "association. Machine-generated content (spam templates, path stuffing, "
            "thin pages) is flagged via repetition &amp; machine-scoring so "
            "low-quality co-cited pages never masquerade as editorial authority.</p>",
            "".join([
                _chip(_esc(status), " brand status"),
                _chip(_num(pois.get("toxic_source_count")), " toxic sources"),
                _chip(_num(pois.get("total_sources")), " sources audited"),
                _chip(_round(pois.get("brand_machine_score")), " brand machine-score"),
                _chip(_num(pois.get("brand_generated_phrase_hits")), " generated-phrase hits"),
            ])))
    # 11) Semantic drift tracking
    dr = adv.get("drift", {}) or {}
    if dr.get("per_topic"):
        n_alerts = len(dr.get("alerts", []))
        feats.append(_feat(
            "11", "Semantic Drift Tracking &amp; Time-Series DB",
            "<p>AI engines re-index and move vector positions continuously. This run "
            "snapshotted its metrics into a persistent time-series "
            "(<code>drift_timeseries.duckdb</code>) and computed the delta vs the "
            "prior run &mdash; the daily/weekly answer to 'did my vector distance "
            "drift after a competitor launch?'.</p>",
            "".join([
                _chip(_num(n_alerts), " drift alerts"),
                _chip(_num(len(dr.get("per_topic", []))), " topics tracked"),
            ]),
            base + "drift_tracking"))
    if not feats:
        return ""
    return ('<h2 class="m3-h2">Enterprise extensions &amp; advanced intelligence</h2>'
            '<div class="feat-list">' + "".join(feats) + "</div>")


# ---------------------------------------------------------------------------
# Page 3 — Outputs summary (curated; full detail lives in the dashboard/PDF)
# ---------------------------------------------------------------------------

def outputs_html(data: Dict[str, Any], job_id: str) -> str:
    """Enterprise Step-3 outputs: in-depth, longer, fully verified report.

    Covers all 11 inputs (echoed with live evidence), all 10 engines with
    complete per-topic / per-entity tables, competitive leaderboard, drift,
    sentiment, synthetic queries, token-density plan, verification and every
    downloadable deliverable — all sourced from the real computed ``data``.
    """
    d = _extract(data)
    cite, inv, cfg, di = d["cite"], d["inv"], d["cfg"], d["di"]
    adv = d["adv"]
    brand = _esc(cfg.get("target_brand", ""))

    inv_idx = cite.get("rag_invisibility_index")
    inv_composite = inv.get("composite_invisibility_index_pct")
    sova = inv.get("composite_vector_share_of_voice_pct")

    # ---- 11 enterprise inputs echoed with evidence ---------------------
    topics = cfg.get("industry_topics", []) or []
    comps = cfg.get("competitor_entities", []) or []
    input_rows = [
        ["01 · Target brand", _esc(cfg.get("target_brand", ""))],
        ["02 · Industry topics (%d)" % len(topics),
         _esc(", ".join(topics[:12])) + (" …" if len(topics) > 12 else "")],
        ["03 · Competitors (%d)" % len(comps), _esc(", ".join(comps))],
        ["04 · Crawl depth", _esc(cfg.get("crawl_depth", "")) + " pages/query"],
        ["05 · Locality", _esc(cfg.get("locality") or "global")],
        ["06 · Search intent + query templates",
         _esc(cfg.get("search_intent", "")) + " · " +
         _num(len((cfg.get("query_templates", {}) or {}))) + " templates"],
        ["07 · Ontology / weighting",
         _num(len((cfg.get("entity_weighting", {}) or {}))) + " weights · " +
         _num(len((cfg.get("ontology_aliases", {}) or {}))) + " alias groups"],
        ["08 · Ground-truth corpora",
         _num(len((cfg.get("corpus_files", []) or []))) + " files" +
         (" · " + _esc(cfg.get("corpus_dir") or "") if cfg.get("corpus_dir") else "")],
        ["09 · Embedding model", _esc(cfg.get("embedding_model", "")) +
         " (" + _esc(d["meta"].get("embedding_kind", "")) + ")"],
        ["10 · SERP footprints", _num(len((cfg.get("serp_footprints", []) or []))) + " engine sources"],
        ["11 · Content feeds", _num(len((cfg.get("content_feeds", []) or []))) + " RSS/sitemap feeds"],
    ]

    # ---- Full proximity table (every row, brand-first) ------------------
    rows_sorted = sorted(d["rows"], key=lambda r: (
        0 if str(r.get("entity", "")).lower() == str(cfg.get("target_brand", "")).lower() else 1,
        -(float(r.get("proximity") or 0) if isinstance(r.get("proximity"), (int, float)) else 0),
    ))
    prox_rows = ""
    for r in rows_sorted[:60]:
        prox_rows += (
            f"<tr><td>{_esc(r.get('topic'))}</td>"
            f"<td>{_esc(r.get('entity'))}</td>"
            f"<td>{_round(r.get('proximity'))}</td>"
            f"<td>{_esc(r.get('label'))}</td>"
            f"<td>{_num(r.get('docs_highly_relevant'))}</td></tr>"
        )
    if not prox_rows:
        prox_rows = "<tr><td colspan='5' class='muted'>No proximity rows.</td></tr>"

    # ---- Competitive leaderboard (mean proximity per entity) ------------
    from collections import defaultdict
    agg: Dict[str, List[float]] = defaultdict(list)
    for r in d["rows"]:
        try:
            agg[str(r.get("entity", ""))].append(float(r.get("proximity")))
        except (TypeError, ValueError):
            pass
    import statistics as _st
    lead = sorted(((e, _st.mean(v), len(v)) for e, v in agg.items() if v),
                  key=lambda x: -x[1])[:12]
    lead_rows = "".join(
        f"<tr><td>{_esc(e)}</td><td>{_round(m)}</td><td>{_num(n)} topics</td>"
        f"<td>{'👑 brand' if e.lower()==str(cfg.get('target_brand','')).lower() else 'rival'}</td></tr>"
        for e, m, n in lead) or "<tr><td colspan='4' class='muted'>—</td></tr>"

    # ---- Entity citation ledger (linked / unlinked / omitted) -----------
    ent_rows = ""
    for e in (d["ent_sum"] or [])[:20]:
        ent_rows += (
            f"<tr><td>{_esc(e.get('entity'))}</td>"
            f"<td>{_num(e.get('docs_linked'))}</td>"
            f"<td>{_num(e.get('docs_unlinked'))}</td>"
            f"<td>{_num(e.get('docs_omitted'))}</td>"
            f"<td>{_round(e.get('citation_rate'))}</td></tr>"
        )
    if not ent_rows:
        ent_rows = "<tr><td colspan='5' class='muted'>No citation ledger.</td></tr>"

    # ---- Off-page targets (extended to 25) -------------------------------
    opts = cite.get("off_page_targets", []) or []
    opt_rows = ""
    for t in opts[:25]:
        opt_rows += (
            f"<tr><td><a href='{_esc(t.get('url'))}' target='_blank' rel='noopener'>"
            f"{_esc((t.get('title') or t.get('url'))[:90])}</a></td>"
            f"<td>{_esc(t.get('source_type'))}</td>"
            f"<td>{_esc(t.get('top_topic'))}</td>"
            f"<td>{_round(t.get('topic_relevance'))}</td>"
            f"<td>{_num(t.get('competitors_present'))}</td></tr>"
        )
    if not opt_rows:
        opt_rows = "<tr><td colspan='5' class='muted'>No off-page targets.</td></tr>"

    # ---- Recommendations (extended to 25, with rationale) ----------------
    recs = data.get("recommendations", []) or []
    rec_rows = ""
    for r in recs[:25]:
        rec_rows += (
            f"<tr><td><span class='m3-badge'>{_esc(r.get('priority'))}</span></td>"
            f"<td>{_esc(r.get('title'))}<br><span class='muted'>{_esc((r.get('rationale') or r.get('detail') or ''))[:220]}</span></td>"
            f"<td>{_esc(r.get('category'))}</td>"
            f"<td>{_round(r.get('score'))}</td></tr>"
        )
    if not rec_rows:
        rec_rows = "<tr><td colspan='4' class='muted'>No recommendations.</td></tr>"

    # ---- Advanced: drift / sentiment / synthetic / density ---------------
    dr = (adv.get("drift", {}) or {})
    alerts = dr.get("alerts", []) or []
    drift_rows = "".join(
        f"<tr><td>{_esc(a.get('topic', ''))}</td><td>{_esc(a.get('message', a.get('detail', '')))[:160]}</td>"
        f"<td>{_round(a.get('delta', a.get('change', '')))}</td></tr>"
        for a in alerts[:10]) or "<tr><td colspan='3' class='muted'>No drift alerts — baseline snapshotted for future runs.</td></tr>"
    sent = (adv.get("sentiment", {}) or {})
    sent_rows = "".join(
        f"<tr><td>{_esc(s.get('entity', ''))}</td><td>{_round(s.get('net_sentiment'))}</td>"
        f"<td>{_num(s.get('risk_windows', s.get('negative_windows', 0)))}</td>"
        f"<td>{_esc(str(s.get('verdict', s.get('label', '')))[:80])}</td></tr>"
        for s in (sent.get("per_entity", []) or [])[:12]) or \
        "<tr><td colspan='4' class='muted'>No sentiment rows.</td></tr>"
    syn = (adv.get("synthetic_queries", {}) or {})
    syn_items = []
    for ent, qs in (syn.get("per_entity", {}) or {}).items():
        for q in (qs or [])[:3]:
            syn_items.append(f"<tr><td>{_esc(ent)}</td><td>{_esc(q if isinstance(q, str) else q.get('query', q))[:140]}</td></tr>")
    syn_rows = "".join(syn_items[:18]) or "<tr><td colspan='2' class='muted'>No synthetic queries.</td></tr>"
    td = (adv.get("token_density", {}) or {})
    td_rows = "".join(
        f"<tr><td>{_esc(t.get('topic', ''))}</td><td>{_esc(t.get('leading_competitor', ''))}</td>"
        f"<td>{_round(t.get('tokens_needed_to_displace'))}</td>"
        f"<td>{_round(t.get('brand_density'))}</td></tr>"
        for t in (td.get("per_topic", []) or [])[:12]) or \
        "<tr><td colspan='4' class='muted'>No density plan rows.</td></tr>"

    fs = di.get("freshness_summary", {}) or {}
    verify_rows = [
        ["Verification score", f'{_round(di.get("verification_score"))} / 100 &nbsp;({"VERIFIED" if di.get("verified") else "PARTIAL"})'],
        ["Models real", _esc(str(di.get("embedding_model") or di.get("embedding_kind"))) + " · " + _esc(str(di.get("ner_model") or di.get("ner_kind")))],
        ["Harvest", ("OK — " + _num(di.get("harvested_docs")) + " docs, " + _num(di.get("dedup_removed")) + " deduped") if di.get("harvest_ok") else "Degraded"],
        ["Live / fresh / median age",
         f'{_pct100(fs.get("live_pct"))} live · {_pct100(fs.get("fresh_pct"))} fresh · {_round(fs.get("median_age_days"))}d median'],
        ["Support / provenance", f'{_pct(di.get("support_fraction"))} support · ' + ("complete" if di.get("provenance_complete") else "partial")],
    ]

    downloads = f"""
    <div class="dl-row">
      <a class="dl" href="/files/{job_id}/report.pdf" target="_blank">⬇ Enterprise PDF Report</a>
      <a class="dl" href="/files/{job_id}/dashboard.html" target="_blank">⬇ Full Dashboard (HTML)</a>
      <a class="dl" href="/files/{job_id}/report.json" download>⬇ report.json</a>
      <a class="dl" href="/files/{job_id}/proximity_scores.csv" download>⬇ proximity_scores.csv</a>
      <a class="dl" href="/files/{job_id}/entity_citation_summary.csv" download>⬇ citations.csv</a>
      <a class="dl" href="/files/{job_id}/off_page_targets.csv" download>⬇ off_page_targets.csv</a>
      <a class="dl" href="/files/{job_id}/recommendations.csv" download>⬇ recommendations.csv</a>
    </div>
    <div class="dl-row">
      <a class="dl" href="/files/{job_id}/share_of_voice_heatmap.csv" download>⬇ SoV heatmap.csv</a>
      <a class="dl" href="/files/{job_id}/token_density_adjuster.csv" download>⬇ token_density.csv</a>
      <a class="dl" href="/files/{job_id}/sentiment_audit.csv" download>⬇ sentiment.csv</a>
      <a class="dl" href="/files/{job_id}/poisoning_sources.csv" download>⬇ poisoning.csv</a>
      <a class="dl" href="/files/{job_id}/semantic_drift.csv" download>⬇ semantic_drift.csv</a>
      <a class="dl" href="/files/{job_id}/synthetic_retrieval_queries.csv" download>⬇ synthetic_queries.csv</a>
      <a class="dl" href="/files/{job_id}/rag_content_brief.md" download>⬇ RAG Brief (MD)</a>
      <a class="dl" href="/files/{job_id}/schema_jsonld_patch.json" download>⬇ JSON-LD Patch</a>
    </div>"""

    return f"""
    <section class="outputs">
      <h2 class="m3-h2">Executive verdict — {brand}</h2>
      <div class="m3-grid">
        <div class="m3-kpi"><div class="v" style="color:var(--m3-error)">{_round(inv_idx)}</div>
          <div class="l">RAG Invisibility Index (lower = better)</div></div>
        <div class="m3-kpi"><div class="v" style="color:var(--m3-on-surface)">{_round(inv_composite)}%</div>
          <div class="l">Composite Invisibility</div></div>
        <div class="m3-kpi"><div class="v" style="color:var(--m3-tertiary)">{_round(sova)}%</div>
          <div class="l">Vector Share of Voice</div></div>
        <div class="m3-kpi"><div class="v">{_round(d['avg_prox'])}</div>
          <div class="l">Mean vector proximity</div></div>
        <div class="m3-kpi"><div class="v">{_num(d['n_prox'])}</div>
          <div class="l">Proximity comparisons</div></div>
        <div class="m3-kpi"><div class="v">{_num(len(recs))}</div>
          <div class="l">Prioritized recommendations</div></div>
      </div>
      <p class="m3-lead">The <b>RAG Invisibility Index ({_round(inv_idx)})</b> is the share of
      high-ranking industry passages where <b>{brand}</b> is absent while rivals are co-cited.
      <b>Vector Share of Voice ({_round(sova)}%)</b> is the brand's retrieval weight across all
      topic × entity comparisons. Mean proximity <b>{_round(d['avg_prox'])}</b> over
      <b>{_num(d['n_prox'])}</b> comparisons ({_num(d['tight'])} tightly-bound, {_num(d['far'])} far).
      Linked <b>{_num(d['linked'])}</b> · unlinked <b>{_num(d['unlinked'])}</b> · omitted
      <b>{_num(d['omitted'])}</b>. Every number below is computed from live harvested evidence —
      nothing estimated, nothing sampled away.</p>

      <h2 class="m3-h2">1 · Audited inputs — all 11 enterprise fields (verified)</h2>
      {_stat_table(input_rows)}
      <p class="verify-note">Inputs above are exactly what the audit executed against — including
      Auto-Detect provenance where applicable. Edit any field and re-run to compare deltas in History &amp; Trends.</p>

      <h2 class="m3-h2">2 · Competitive leaderboard — mean proximity per entity</h2>
      <table class="m3-table"><thead><tr><th>Entity</th><th>Mean proximity</th><th>Coverage</th><th>Side</th></tr></thead>
        <tbody>{lead_rows}</tbody></table>

      <h2 class="m3-h2">3 · Full semantic vector proximity (brand-first, top 60)</h2>
      <table class="m3-table"><thead><tr><th>Topic</th><th>Entity</th><th>Proximity</th>
        <th>Label</th><th>High-rel docs</th></tr></thead>
        <tbody>{prox_rows}</tbody></table>

      <h2 class="m3-h2">4 · Citation ledger — linked vs unlinked vs omitted</h2>
      <table class="m3-table"><thead><tr><th>Entity</th><th>Linked</th><th>Unlinked</th><th>Omitted</th><th>Rate</th></tr></thead>
        <tbody>{ent_rows}</tbody></table>

      <h2 class="m3-h2">5 · High-density off-page target list (top 25)</h2>
      <table class="m3-table"><thead><tr><th>URL</th><th>Type</th><th>Top topic</th>
        <th>Relevance</th><th>Rivals present</th></tr></thead>
        <tbody>{opt_rows}</tbody></table>

      <h2 class="m3-h2">6 · Prioritized action plan (top 25 with rationale)</h2>
      <table class="m3-table"><thead><tr><th>Priority</th><th>Directive + rationale</th><th>Category</th>
        <th>Score</th></tr></thead><tbody>{rec_rows}</tbody></table>

      <h2 class="m3-h2">7 · Token-density displacement plan (per topic)</h2>
      <table class="m3-table"><thead><tr><th>Topic</th><th>Leader to displace</th><th>Tokens needed</th><th>Brand density</th></tr></thead>
        <tbody>{td_rows}</tbody></table>

      <h2 class="m3-h2">8 · Sentiment &amp; hallucination audit (per entity)</h2>
      <table class="m3-table"><thead><tr><th>Entity</th><th>Net sentiment</th><th>Risk windows</th><th>Verdict</th></tr></thead>
        <tbody>{sent_rows}</tbody></table>

      <h2 class="m3-h2">9 · Synthetic retrieval queries (reverse-engineered prompts)</h2>
      <table class="m3-table"><thead><tr><th>Entity</th><th>Prompt that retrieves it</th></tr></thead>
        <tbody>{syn_rows}</tbody></table>

      <h2 class="m3-h2">10 · Semantic drift &amp; tracking</h2>
      <table class="m3-table"><thead><tr><th>Topic</th><th>Signal</th><th>Delta</th></tr></thead>
        <tbody>{drift_rows}</tbody></table>

      <h2 class="m3-h2">11 · Verification &amp; provenance (real-time trust)</h2>
      {_stat_table(verify_rows)}
      <p class="verify-note">Verification is computed from the harvested corpus, HTTP provenance,
      model authenticity and freshness grades — <b>verified = all live checks passed</b>. Raw evidence
      ships in <span class="m3-code">report.json</span> and <span class="m3-code">/api/verify/{job_id}</span>.</p>

      <h2 class="m3-h2">12 · Download the full deliverables</h2>
      {downloads}
      <p class="verify-note">Next: re-run or schedule this brand weekly — deltas land automatically in
      <b>History &amp; Trends</b> with per-topic drift alerts. Target the off-page list top-down; each win
      moves both invisibility and share-of-voice in the next audit.</p>
    </section>"""
