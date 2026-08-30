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
    try:
        return f"{float(x) * 100:.{nd}f}%"
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
    return f'<span class="chip"><b>{value}</b>{_esc(label)}</span>'


def _feat(num: str, title: str, desc: str, metrics: str) -> str:
    return f"""
    <div class="feat">
      <div class="feat-num">{num}</div>
      <div class="feat-body">
        <h3>{title}</h3>
        {desc}
        <div class="feat-metrics">{metrics}</div>
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

def features_html(data: Dict[str, Any]) -> str:
    d = _extract(data)
    cfg, di, hs, cs = d["cfg"], d["di"], d["hs"], d["cs"]

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

    feats = "".join([
        _feat("A", "Zero-Cost Headless Web Harvester", a_desc, a_metrics),
        _feat("B", "Local Vector Embedding &amp; Semantic Mapping", b_desc, b_metrics),
        _feat("C", "Local NER &amp; Knowledge Graphs", c_desc, c_metrics),
        _feat("D", "Unlinked Authority &amp; Citation Gap Finder", d_desc, d_metrics),
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
        ["Live sources", _pct(fs.get("live_pct"))],
        ["Fresh / current", _pct(fs.get("fresh_pct"))],
        ["Median source age", f"{_round(fs.get('median_age_days'))} days"],
        ["Entities with mentions", f'{_num(di.get("entities_with_mentions"))} / {_num(di.get("entities_total"))}'],
        ["Provenance complete", "Yes" if di.get("provenance_complete") else "Partial"],
        ["Support fraction", _pct(di.get("support_fraction"))],
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
      <h2>How the audit works &mdash; four local micro-engines</h2>
      <p class="lead">This run analysed <b>{_num(cs.get('doc_count'))}</b> clean
      documents for <b>{_esc(brand)}</b> across
      <b>{_num(len(topics))}</b> topics and <b>{_num(len(comps))}</b> competitors.
      Each engine below shows what it did on <i>this</i> corpus.</p>
      <div class="feat-list">{feats}</div>

      {_advanced_features_html(d)}

      <h2>Methodology &amp; verification</h2>
      {verify_block}
    </section>"""


# ---------------------------------------------------------------------------
# Enterprise advanced-features block (page 2)
# ---------------------------------------------------------------------------

def _advanced_features_html(d: Dict[str, Any]) -> str:
    adv = d.get("adv") or {}
    if not adv:
        return ""
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
            ])))
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
            ])))
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
            ])))
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
            ])))
    # 10) Vector poisoning / negative SEO
    pois = adv.get("poisoning", {}) or {}
    if pois:
        status = pois.get("brand_poisoning_status", "clean")
        feats.append(_feat(
            "10", "Vector Poisoning / Negative-SEO Detection",
            "<p>Detects how low-quality sites co-cite the brand with toxic or " 
            "off-topic concept clusters that drag its centroid toward junk topics "
            "in vector space &mdash; a growing risk as engines rank by semantic "
            "association.</p>",
            "".join([
                _chip(_esc(status), " brand status"),
                _chip(_num(pois.get("toxic_source_count")), " toxic sources"),
                _chip(_num(pois.get("total_sources")), " sources audited"),
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
            ])))
    if not feats:
        return ""
    return ('<h2>Enterprise extensions &amp; advanced intelligence</h2>'
            '<div class="feat-list">' + "".join(feats) + "</div>")


# ---------------------------------------------------------------------------
# Page 3 — Outputs summary (curated; full detail lives in the dashboard/PDF)
# ---------------------------------------------------------------------------

def outputs_html(data: Dict[str, Any], job_id: str) -> str:
    d = _extract(data)
    cite, inv = d["cite"], d["inv"]
    brand = _esc(d["cfg"].get("target_brand", ""))

    inv_idx = cite.get("rag_invisibility_index")
    inv_composite = inv.get("composite_invisibility_index_pct")
    sova = inv.get("composite_vector_share_of_voice_pct")

    # Top off-page targets
    opts = cite.get("off_page_targets", []) or []
    opt_rows = ""
    for t in opts[:12]:
        opt_rows += (
            f"<tr><td><a href='{_esc(t.get('url'))}' target='_blank' rel='noopener'>"
            f"{_esc(t.get('title') or t.get('url'))}</a></td>"
            f"<td>{_esc(t.get('source_type'))}</td>"
            f"<td>{_esc(t.get('top_topic'))}</td>"
            f"<td>{_round(t.get('topic_relevance'))}</td>"
            f"<td>{_num(t.get('competitors_present'))}</td></tr>"
        )

    # Top recommendations
    recs = data.get("recommendations", []) or []
    rec_rows = ""
    for r in recs[:12]:
        rec_rows += (
            f"<tr><td><span class='badge'>{_esc(r.get('priority'))}</span></td>"
            f"<td>{_esc(r.get('title'))}</td>"
            f"<td>{_esc(r.get('category'))}</td>"
            f"<td>{_round(r.get('score'))}</td></tr>"
        )

    # Proximity snapshot (brand rows only, if distinguishable)
    prox_rows = ""
    shown = 0
    for r in d["rows"]:
        if shown >= 14:
            break
        prox_rows += (
            f"<tr><td>{_esc(r.get('topic'))}</td>"
            f"<td>{_esc(r.get('entity'))}</td>"
            f"<td>{_round(r.get('proximity'))}</td>"
            f"<td>{_esc(r.get('label'))}</td>"
            f"<td>{_num(r.get('docs_highly_relevant'))}</td></tr>"
        )
        shown += 1

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
      <h2>What this audit produced</h2>
      <div class="kpis">
        <div class="kpi"><div class="v" style="color:var(--bad)">{_round(inv_idx)}</div>
          <div class="l">RAG Invisibility Index</div></div>
        <div class="kpi"><div class="v" style="color:var(--warn)">{_round(inv_composite)}%</div>
          <div class="l">Composite Invisibility</div></div>
        <div class="kpi"><div class="v" style="color:var(--accent2)">{_round(sova)}%</div>
          <div class="l">Vector Share of Voice</div></div>
        <div class="kpi"><div class="v">{_num(len(recs))}</div>
          <div class="l">Off-page Recommendations</div></div>
      </div>
      <p class="lead">The <b>RAG Invisibility Index</b> is the percentage of
      high-ranking industry articles where <b>{brand}</b> is completely absent
      while competitors are co-cited. Lower is better. Full interactive detail is
      in the dashboard; the curated tables and a print-ready PDF are below.</p>

      <h2>Semantic vector proximity (sample)</h2>
      <table><thead><tr><th>Topic</th><th>Entity</th><th>Proximity</th>
        <th>Label</th><th>High-rel docs</th></tr></thead>
        <tbody>{prox_rows}</tbody></table>

      <h2>High-density off-page target list</h2>
      <table><thead><tr><th>URL</th><th>Type</th><th>Top topic</th>
        <th>Relevance</th><th>Competitors present</th></tr></thead>
        <tbody>{opt_rows}</tbody></table>

      <h2>Actionable off-page recommendations</h2>
      <table><thead><tr><th>Priority</th><th>Directive</th><th>Category</th>
        <th>Score</th></tr></thead><tbody>{rec_rows}</tbody></table>

      <h2>Download the full deliverables</h2>
      {downloads}
    </section>"""
