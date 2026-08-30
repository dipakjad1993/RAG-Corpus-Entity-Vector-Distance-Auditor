"""Self-contained HTML dashboard.

Renders fully offline (no CDN / JS dependencies) using inline CSS and
server-side-generated bar charts.  Includes:

* KPI summary cards (RAG Invisibility Index, Vector Share of Voice, #docs)
* Semantic Vector Proximity matrix with bars
* Per-topic RAG Invisibility & Share of Voice
* Entity link-vs-mention audit
* High-Density Off-Page Target list
* Prioritized recommendations
"""

from __future__ import annotations

import html
import json
import logging
import os
from typing import Any, Dict, Optional

from ..utils import get_logger

logger = get_logger("ragevda.reporting.dashboard")


def _esc(x) -> str:
    return html.escape(str(x))


def _bar(value: float, max_val: float = 1.0, color: str = "#4f8cff") -> str:
    pct = max(0.0, min(100.0, (value / max_val) * 100.0)) if max_val else 0.0
    return (
        f'<div class="bartrack"><div class="bar" style="width:{pct:.1f}%;'
        f'background:{color}"></div>'
        f'<span class="barval">{value:.2f}</span></div>'
    )


def _label_color(label: str) -> str:
    return {
        "Tightly Bound": "#2ecc71",
        "Moderate": "#f1c40f",
        "Far": "#e74c3c",
    }.get(label, "#888")


def _conf_badge(conf: str) -> str:
    color = {"high": "#2ecc71", "medium": "#f1c40f",
             "low": "#e67e22", "none": "#e74c3c"}.get(conf, "#888")
    return f"<span class='conf conf-{conf}'>{conf}</span>"


def _brand_health_issues(data: Dict[str, Any], brand: str):
    """Derive the concrete gaps the brand must act on, from the real data."""
    issues = []
    hw = data["meta"].get("harvest_warning")
    if hw:
        issues.append(("critical", "No live corpus harvested", hw))
    hs = data["meta"].get("harvest_stats", {})
    if hs.get("empty_queries"):
        issues.append(("warn",
            f"{hs['empty_queries']} of {hs.get('queries', 0)} searches returned 0 results",
            "Some expanded queries (e.g. '… news') had no hits. The harvester "
            "auto-retried simpler variants, but a high count signals DuckDuckGo "
            "rate-limiting — reduce topic count, lower crawl depth, or retry later."))
    for t in data["invisibility"]["per_topic"]:
        if t["relevant_docs"] == 0:
            continue
        if t["topic_invisibility_pct"] >= 50:
            issues.append(("critical",
                f"Brand invisible in '{t['topic']}' ({t['topic_invisibility_pct']}% invisibility)",
                f"Your brand appears in only {t['brand_present_docs']}/{t['relevant_docs']} "
                f"high-relevance articles; competitors appear in {t['competitor_present_docs']}."))
        elif t["topic_invisibility_pct"] >= 25:
            issues.append(("warn",
                f"Weak presence in '{t['topic']}' ({t['topic_invisibility_pct']}% invisibility)",
                f"Brand present in {t['brand_present_docs']}/{t['relevant_docs']} articles."))
        if t["vector_share_of_voice_pct"] < 20:
            issues.append(("warn",
                f"Low Vector Share of Voice in '{t['topic']}' ({t['vector_share_of_voice_pct']}%)",
                "Your brand's semantic footprint is small vs competitors — prioritize "
                "content and off-page work in this topic."))
    for r in data["proximity"]["rows"]:
        if r["entity"] == brand and r["label"] == "Far":
            issues.append(("warn",
                f"Brand semantically 'Far' from '{r['topic']}' (prox {r['proximity']:.2f})",
                "The retrieval model sees little meaning overlap between your brand and "
                "this topic, which hurts the chance of being surfaced by RAG."))
    for e in data["citation_gap"]["entity_summary"]:
        if e["entity"] == brand and e["docs_total"] and e["docs_omitted"] / e["docs_total"] >= 0.5:
            issues.append(("critical",
                f"Brand omitted from {e['docs_omitted']}/{e['docs_total']} articles that cite competitors",
                "Convert unlinked mentions and pursue links on these pages (see Off-Page Targets)."))
    if not data["citation_gap"]["off_page_targets"]:
        issues.append(("info", "No high-density off-page targets found",
            "Few pages cite competitors without you. Broaden topics to surface more "
            "link/mention opportunities."))
    return issues


def _render_advanced(adv: Dict[str, Any], brand: str, cfg: Dict,
                     freshness: Optional[Dict] = None) -> str:
    """Render the enterprise/advanced data sections for the dashboard."""
    if not adv:
        return ""

    parts = []

    # ---- Real-time source freshness / liveness ----------------------
    if freshness and freshness.get("summary"):
        fs = freshness["summary"]
        staleness_colors = {
            "fresh": "#2ecc71", "recent": "#f1c40f",
            "stale": "#e67e22", "aging": "#e74c3c", "unknown": "#95a5a6",
        }
        fr_rows = ""
        pct_map = {"fresh": "fresh_pct", "recent": "recent_pct",
                   "stale": "stale_pct", "aging": "stale_pct"}
        for cat, color in staleness_colors.items():
            key = pct_map.get(cat)
            val = fs.get(key, 0) if key else 0
            fr_rows += (
                f"<div class='kpi'><div class='v' style='color:{color}'>{val}%</div>"
                f"<div class='l'>{cat.title()}</div></div>"
            )
        live_bar = _bar(fs.get("live_pct", 0), 100.0, "#2ecc71")
        parts.append(f"""
        <section><h2>Real-Time Source Freshness &amp; Liveness</h2>
        <div class="kpis">
          <div class="kpi"><div class="v">{fs.get('live_pct',0)}%</div><div class="l">Live (HTTP 2xx)</div></div>
          <div class="kpi"><div class="v">{fs.get('median_age_days','—')}</div><div class="l">Median age (days)</div></div>
          <div class="kpi"><div class="v">{fs.get('max_age_days','—')}</div><div class="l">Oldest source (days)</div></div>
          <div class="kpi"><div class="v">{fs.get('total_sources',0)}</div><div class="l">Sources checked</div></div>
        </div>
        <div class="kpis">{fr_rows}</div>
        <div class="bar-row"><span class="bar-label">Live data share</span>{live_bar}<span>{fs.get('live_pct',0)}%</span></div>
        <div class="footer">{_esc(fs.get('method',''))}</div></section>""")

    # ---- Engine-matrix Share of Voice heatmap ----------------------
    eng = adv.get("engine_matrix", {}) or {}
    cells = eng.get("cells", []) or []
    if cells:
        topics = list(dict.fromkeys(c["topic"] for c in cells))
        engines = list(dict.fromkeys(c["engine"] for c in cells))
        head = "".join(f"<th>{_esc(e)}</th>" for e in engines)
        rows = ""
        for t in topics:
            tds = ""
            for e in engines:
                c = next((x for x in cells if x["topic"] == t and x["engine"] == e), None)
                if c is None:
                    tds += "<td class='muted'>—</td>"
                else:
                    v = c["vector_sov_pct"]
                    color = "#1abc9c" if v >= 50 else ("#f1c40f" if v >= 25 else "#e74c3c")
                    tds += (
                        f"<td><b style='color:{color}'>{v}%</b>"
                        f"<div class='muted' style='font-size:10px'>{c['relevant_docs']} docs</div></td>"
                    )
            rows += f"<tr><td>{_esc(t)}</td>{tds}</tr>"
        parts.append(f"""
        <section><h2>Vector Share of Voice — topic × AI-engine matrix</h2>
        <table><thead><tr><th>Topic</th>{head}</tr></thead><tbody>{rows}</tbody></table>
        <div class="footer">Green ≥ 50%, amber 25–49%, red &lt; 25% brand dominance.
        SoV numbers are computed from real on-page retrieval features (authority,
        recency, verbosity, title-directness, entity-richness) measured live from
        the corpus; the engine differences are emergent, not a fixed affinity table.
        Confidence scales with on-topic evidence volume.</div></section>""")

    # ---- Token-density adjuster -------------------------------------
    dens = adv.get("token_density", {}).get("per_topic", []) or []
    if dens:
        drows = ""
        for d in dens:
            ds = d["density_gap_ratio"]
            drows += (
                f"<tr class='row-{ 'bad' if d['severity']=='critical' else ('warn' if d['severity']=='high' else 'good') }'"
                f"><td>{_esc(d['topic'])}</td><td>{_esc(d['leading_competitor'] or '—')}</td>"
                f"<td>{d['brand_on_window_usage_tokens']}</td><td>{d['leader_on_window_usage_tokens']}</td>"
                f"<td>{_bar(d['brand_density'], max(d['leader_density'], d['brand_density'], 0.01) or 1.0, '#4f8cff')}</td>"
                f"<td>{d['tokens_needed_to_displace']}</td><td>{_esc(d['severity'])}</td></tr>"
            )
        parts.append(f"""
        <section><h2>Automated Token-Density Adjuster</h2>
        <p class="muted">Tokens the brand occupies within a retrieval window
        (512-token simulated RAG chunks) versus the leading competitor, and how
        many more on-window tokens are needed to displace them from top-{cfg.get('top_k_retrieval',5)} retrieval.</p>
        <table><thead><tr><th>Topic</th><th>Leader</th><th>Brand tokens</th>
        <th>Leader tokens</th><th>Brand density</th><th>Tokens needed</th><th>Severity</th></tr></thead>
        <tbody>{drows}</tbody></table>
        <div class="footer">Composite displacement readiness:
        <b>{adv.get('token_density', {}).get('brand_displacement_readiness', 0)}/100</b>
        ({adv.get('token_density', {}).get('method', '')})</div></section>""")

    # ---- Sentiment auditor ------------------------------------------
    sent = adv.get("sentiment", {}) or {}
    sent_sum = sent.get("per_entity", []) or []
    if sent_sum:
        srows = ""
        for s in sent_sum:
            framing_cls = {"positive": "good", "negative": "bad", "neutral": "warn"}.get(s["framing"], "")
            srows += (
                f"<tr><td>{_esc(s['entity'])}</td><td>{s['mentions']}</td>"
                f"<td>{s['positive_pct']}%</td><td>{s['neutral_pct']}%</td>"
                f"<td>{s['negative_pct']}%</td>"
                f"<td><b style='color:{'#2ecc71' if s['net_sentiment']>0.1 else ('#e74c3c' if s['net_sentiment']<-0.1 else '#f1c40f')}'>{s['net_sentiment']:+.3f}</b></td>"
                f"<td class='{framing_cls}'>{s['risk_windows']} risk</td></tr>"
            )
        risks = sent.get("risk_windows", []) or []
        risk_rows = ""
        for r in risks[:6]:
            risk_rows += (
                f"<tr class='row-bad'><td>{_esc(r['entity'])}</td>"
                f"<td class='src'><a href='{_esc(r['url'])}' target='_blank'>{_esc(r['title'][:50])}</a></td>"
                f"<td>{r['polarity']:+.3f}</td><td>{_esc(r['snippet'][:200])}{'…' if len(r['snippet'])>200 else ''}</td></tr>"
            )
        parts.append(f"""
        <section><h2>RAG Chunk Hallucination &amp; Sentiment Auditor</h2>
        <table><thead><tr><th>Entity</th><th>Mentions</th><th>Pos %</th><th>Neu %</th>
        <th>Neg %</th><th>Net Sentiment</th><th>Risk</th></tr></thead><tbody>{srows}</tbody></table>
        {('<h2 style="font-size:15px">Verbatim negative-framed brand windows</h2><table><thead><tr><th>Entity</th><th>Source</th><th>Polarity</th><th>Snippet</th></tr></thead><tbody>' + risk_rows + '</tbody></table>') if risk_rows else ''}
        <div class="footer">Net sentiment ∈ [-1, 1]; negative-framed windows are the
        exact retrieval text that can turn an AI answer against the brand.
        Scored with <b>{_esc(sent.get('method',''))}</b>
        {('(<code>' + _esc(sent.get('model','')) + '</code>)') if sent.get('model') else ''}.</div></section>""")

    # ---- Vector poisoning / negative SEO ----------------------------
    pois = adv.get("poisoning", {}) or {}
    status = pois.get("brand_poisoning_status", "clean")
    status_color = {"clean": "#2ecc71", "at-risk": "#f39c12", "compromised": "#e74c3c"}.get(status, "#888")
    psrc = pois.get("sources", []) or []
    psrc_rows = "".join(
        f"<tr class='row-bad'><td class='src'><a href='{_esc(s['url'])}' target='_blank'>{_esc(s['title'][:50])}</a></td>"
        f"<td>{_esc(s['domain'])}</td><td>{s['poisoning_risk']:.2f}</td><td>{_esc(s['risk_factors'])}</td></tr>"
        for s in psrc[:12]
    )
    exp_rows = "".join(
        f"<tr class='{'row-bad' if e['toxic_share_pct']>=20 else ''}'><td>{_esc(e['entity'])}</td>"
        f"<td>{e['sources_co_cited']}</td><td>{e['toxic_sources']}</td><td>{e['toxic_share_pct']}%</td></tr>"
        for e in pois.get("entity_exposure", []) or []
    )
    parts.append(f"""
    <section><h2>Vector Poisoning / Negative-SEO Detection</h2>
    <p class="muted">Brand poisoning status: <b style="color:{status_color}">{status.upper()}</b>
    &nbsp;·&nbsp; {pois.get('toxic_source_count',0)} toxic source(s) of {pois.get('total_sources',0)} audited.</p>
    {('<h2 style="font-size:15px">Suspicious co-citing sources</h2><table><thead><tr><th>URL</th><th>Domain</th><th>Risk</th><th>Factors</th></tr></thead><tbody>' + psrc_rows + '</tbody></table>') if psrc_rows else ''}
    <h2 style="font-size:15px">Entity exposure</h2>
    <table><thead><tr><th>Entity</th><th>Sources co-cited</th><th>Toxic sources</th><th>Toxic share</th></tr></thead><tbody>{exp_rows}</tbody></table>
    <div class="footer">Detects thin content, link-farm density and off-topic
    toxic co-citation that drag a brand's centroid toward junk topics in vector space.</div></section>""")

    # ---- Semantic drift ---------------------------------------------
    drifts = adv.get("drift", {}).get("per_topic", []) or []
    if drifts:
        drows = ""
        for d in drifts:
            anomaly = '<span style="color:#e74c3c">⚑</span>' if d.get("anomaly") else ""
            drows += (
                f"<tr><td>{_esc(d['topic'])} {anomaly}</td><td>{d['proximity']:.3f}</td>"
                f"<td>{d['proximity_delta']:+.3f}</td><td>{d['invisibility_pct']}%</td>"
                f"<td>{d['invisibility_delta']:+.1f}</td><td>{d['sov_pct']}%</td>"
                f"<td>{d['sov_delta']:+.1f}</td><td>{d['trend_proximity_per_run']:+.4f}/run</td>"
                f"<td>{d.get('data_points',0)}</td>"
                f"<td>{'yes' if d.get('has_prior') else 'no baseline'}</td></tr>"
            )
        alerts = adv.get("drift", {}).get("alerts", []) or []
        alert_html = ""
        for a in alerts:
            alert_html += f"<div class='issue {'warn' if not a.get('proximity_delta') else 'error'}'><div class='issue-title'>Drift alert: {_esc(a['topic'])}</div><div class='issue-detail'>{_esc(a['reason'])}</div></div>"
        parts.append(f"""
        <section><h2>Semantic Drift Tracking (time-series deltas &amp; trends)</h2>
        {f'<div class="issues">{alert_html}</div>' if alert_html else ''}
        <table><thead><tr><th>Topic</th><th>Proximity</th><th>Δ Prox</th><th>Invis %</th>
        <th>Δ Invis</th><th>SoV %</th><th>Δ SoV</th><th>Trend prox/run</th><th># runs</th><th>Prior</th></tr></thead>
        <tbody>{drows}</tbody></table>
        <div class="footer">Δ vs the most recent prior run for the same brand+topic
        (persisted in <code>drift_timeseries.duckdb</code>). 'Trend prox/run' is a real
        linear-regression slope over the full history; '⚑' marks a z-score anomaly
        (|z| ≥ 2). Only data points from real runs contribute.</div></section>""")

    # ---- Synthetic queries ------------------------------------------
    syn = adv.get("synthetic_queries", {}).get("per_entity", {}) or {}
    if syn:
        syn_rows = ""
        for ent, qs in syn.items():
            for q in qs[:4]:
                syn_rows += (
                    f"<tr><td>{_esc(ent)}</td><td>{_esc(q['query'])}</td>"
                    f"<td>{_esc(q['topic'])}</td><td>{_esc(q['type'])}</td>"
                    f"<td>{_bar(q['retrieval_confidence'], 1.0)}</td></tr>"
                )
        parts.append(f"""
        <section><h2>Synthetic Query Generator (reverse-engineered RAG prompts)</h2>
        <p class="muted">The retrieval prompts an AI engine is likely issuing to pull
        each entity's chunks. Use the brand-targeted ones as Q&amp;A / FAQ content targets.</p>
        <table><thead><tr><th>Entity</th><th>Query</th><th>Topic</th><th>Type</th><th>Retrieval confidence</th></tr></thead>
        <tbody>{syn_rows}</tbody></table></section>""")

    # ---- Chunking simulator summary ---------------------------------
    ch = adv.get("chunking", {}) or {}
    if ch:
        parts.append(f"""
        <section><h2>RAG Chunking &amp; Contextual-Window Simulator</h2>
        <div class="kpis">
          <div class="kpi"><div class="v">{ch.get('window_count',0)}</div><div class="l">Token windows</div></div>
          <div class="kpi"><div class="v">{ch.get('retrieved_count',0)}</div><div class="l">Top-k retrieved</div></div>
          <div class="kpi"><div class="v">{ch.get('tokens_processed',0)}</div><div class="l">Tokens processed</div></div>
          <div class="kpi"><div class="v">{ch.get('chunk_tokens',512)}</div><div class="l">Chunk size (tokens)</div></div>
        </div>
        <div class="footer">Documents are split into {ch.get('chunk_tokens','?')}-token windows with
        {ch.get('chunk_overlap_tokens','?')}-token overlap before scoring, mirroring how real RAG
        retrievers embed individual windows rather than whole articles.</div></section>""")

    # ---- LLM rationale ----------------------------------------------
    llm = adv.get("llm", {}) or {}
    if not llm.get("available"):
        parts.append(f"""
        <section><h2>Local-LLM Gap Analysis</h2>
        <p class="muted">{_esc(llm.get('note', 'Local LLM not available.'))}</p></section>""")

    return "\n".join(parts)


def render_dashboard(data: Dict[str, Any]) -> str:
    cfg = data["meta"]["config"]
    prox = data["proximity"]
    cit = data["citation_gap"]
    inv = data["invisibility"]
    recs = data["recommendations"]
    ctx_stats = data["meta"]["context_stats"]
    brand = cfg["target_brand"]

    # ---- proximity matrix rows -------------------------------------
    prox_rows = ""
    for r in prox["rows"]:
        src = r.get("top_sources") or []
        src_html = "<br>".join(
            f"<a href='{_esc(s['url'])}' target='_blank'>{_esc(s['title'][:55])}</a>"
            f" <span class='rel'>({s['topic_relevance']:.2f})</span>"
            for s in src[:2]
        ) if src else "<span class='muted'>no mentions in corpus</span>"
        row_cls = ""
        if r["entity"] == brand and r["label"] == "Far":
            row_cls = "row-bad"
        elif r["entity"] == brand and r["label"] == "Tightly Bound":
            row_cls = "row-good"
        prox_rows += (
            f"<tr class='{row_cls}'><td>{_esc(r['topic'])}</td><td>{_esc(r['entity'])}</td>"
            f"<td>{_bar(r['proximity'], 1.0, _label_color(r['label']))}</td>"
            f"<td>{_esc(r['label'])}</td>"
            f"<td>{r['docs_highly_relevant']}</td>"
            f"<td>{r.get('support_mentions', 0)}</td>"
            f"<td>{_conf_badge(r.get('confidence', 'none'))}</td>"
            f"<td class='src'>{src_html}</td></tr>"
        )

    # ---- entity citation summary -----------------------------------
    ent_rows = ""
    for e in cit["entity_summary"]:
        row_cls = ""
        if e["entity"] == brand and e["docs_total"] and e["docs_omitted"] / e["docs_total"] >= 0.5:
            row_cls = "row-bad"
        ent_rows += (
            f"<tr class='{row_cls}'><td>{_esc(e['entity'])}</td>"
            f"<td>{e['docs_mentioned']}/{e['docs_total']}</td>"
            f"<td>{e['docs_linked']}</td><td>{e['docs_unlinked']}</td>"
            f"<td>{e['docs_omitted']}</td>"
            f"<td>{_bar(e['mention_rate_pct'], 100.0, '#9b59b6')}</td>"
            f"<td>{e['link_rate_of_mentions_pct']}%</td></tr>"
        )

    # ---- invisibility per topic -----------------------------------
    inv_rows = ""
    for t in inv["per_topic"]:
        row_cls = ""
        if t["relevant_docs"] and t["topic_invisibility_pct"] >= 50:
            row_cls = "row-bad"
        elif t["relevant_docs"] and t["topic_invisibility_pct"] >= 25:
            row_cls = "row-warn"
        inv_rows += (
            f"<tr class='{row_cls}'><td>{_esc(t['topic'])}</td><td>{t['relevant_docs']}</td>"
            f"<td>{t['brand_present_docs']}</td>"
            f"<td>{t['competitor_present_docs']}</td>"
            f"<td>{_bar(t['vector_share_of_voice_pct'], 100.0, '#1abc9c')}</td>"
            f"<td>{_bar(t['topic_invisibility_pct'], 100.0, '#e67e22')}</td>"
            f"<td>{t.get('threshold_used', '')}</td></tr>"
        )

    # ---- off-page targets -----------------------------------------
    tgt_rows = ""
    for i, t in enumerate(cit["off_page_targets"][:25], 1):
        comps = ", ".join(t["competitors_present"]) or "—"
        tgt_rows += (
            f"<tr><td>{i}</td><td><a href='{_esc(t['url'])}' target='_blank'>"
            f"{_esc(t['title'][:70])}</a></td><td>{_esc(t['source_type'])}</td>"
            f"<td>{_esc(t['top_topic'])}</td>"
            f"<td>{_bar(t['topic_relevance'], 1.0)}</td>"
            f"<td>{_esc(comps)}</td></tr>"
        )
    if not tgt_rows:
        tgt_rows = "<tr><td colspan='6' class='muted'>No off-page targets identified.</td></tr>"

    # ---- data provenance / sources ---------------------------------
    prov_rows = ""
    for i, s in enumerate(data.get("provenance", []), 1):
        status = s.get("http_status", "")
        status_cls = "row-good" if status == 200 else ("row-warn" if status else "")
        prov_rows += (
            f"<tr><td>{i}</td><td>{_esc(s.get('domain', ''))}</td>"
            f"<td>{_esc(s.get('source_type', ''))}</td>"
            f"<td>{_esc(s.get('top_topic', ''))}</td>"
            f"<td>{_bar(s.get('top_topic_relevance', 0.0), 1.0)}</td>"
            f"<td>{s.get('chars', 0)}</td>"
            f"<td class='{status_cls}'>{status or 'n/a'}</td>"
            f"<td class='src'><a href='{_esc(s.get('url', ''))}' target='_blank'>"
            f"{_esc(s.get('title', '')[:60])}</a></td></tr>"
        )
    if not prov_rows:
        prov_rows = "<tr><td colspan='8' class='muted'>No sources harvested.</td></tr>"

    # ---- recommendations ------------------------------------------
    rec_html = ""
    for r in recs:
        rec_html += (
            f"<div class='rec {str(r['priority']).lower()}'>"
            f"<div class='rec-head'><span class='badge'>P{r['priority']}</span>"
            f"#{r['rank']} &nbsp; <b>{_esc(r['title'])}</b>"
            f" <span class='cat'>{_esc(r['category'])}</span></div>"
            f"<div class='rec-body'>{_esc(r['rationale'])}</div>"
            f"<div class='rec-action'><b>Action:</b> {_esc(r['action'])}</div>"
            f"</div>"
        )
    if not rec_html:
        rec_html = "<p class='muted'>No recommendations generated.</p>"

    # ---- brand health issues --------------------------------------
    issues = _brand_health_issues(data, brand)
    if issues:
        issue_cards = ""
        for sev, title, detail in issues:
            issue_cards += (
                f"<div class='issue {sev}'><div class='issue-title'>{_esc(title)}</div>"
                f"<div class='issue-detail'>{_esc(detail)}</div></div>"
            )
    else:
        issue_cards = "<div class='issue good'><div class='issue-title'>No critical gaps detected</div>" \
                      "<div class='issue-detail'>Your brand is well represented across the analyzed corpus.</div></div>"

    # ---- harvest transparency -------------------------------------
    hs = data["meta"].get("harvest_stats", {})
    harvest_line = (
        f"Search queries issued: <b>{hs.get('queries', 0)}</b> &nbsp;|&nbsp; "
        f"queries with 0 results: <b>{hs.get('empty_queries', 0)}</b> &nbsp;|&nbsp; "
        f"candidate pages: <b>{hs.get('candidates', 0)}</b> &nbsp;|&nbsp; "
        f"clean docs fetched: <b>{hs.get('fetched', 0)}</b> &nbsp;|&nbsp; "
        f"page cap (max_pages): <b>{cfg.get('max_pages', 0)}</b> "
        f"(0 = unlimited)"
    )

    # ---- methodology (Feature A–D + outputs) -----------------------
    methodology = f"""
    <div class="method">
      <h3>Feature A — Zero-Cost Headless Web Harvester</h3>
      <p><b>What it does:</b> Pulls the top web pages, Reddit discussions and news
      articles via DuckDuckGo (no API key) and optionally a local SearXNG instance,
      then strips headers, footers, sidebars and ads with trafilatura/BeautifulSoup
      to keep only the pure body text a RAG crawler would actually ingest.</p>
      <p><b>Why we analyze it:</b> Your visibility in a RAG answer is only as good as
      the pages the retriever can find and clean. Dirty or unreachable pages
      silently drop you from the corpus.</p>
      <p><b>What to do:</b> If searches return 0 (rate-limited), reduce topics or
      retry; supply a local corpus folder as a guaranteed fallback.</p>

      <h3>Feature B — Local Vector Embedding &amp; Semantic Mapping</h3>
      <p><b>What it does:</b> sentence-transformers (all-MiniLM-L6-v2 / bge-small) runs
      locally on CPU/GPU and converts paragraphs, your brand and topics into vectors;
      cosine similarity (0.00 = unrelated, 1.00 = identical) measures proximity.</p>
      <p><b>Why we analyze it:</b> Retrieval is similarity-based. Low brand–topic
      proximity means a RAG system is unlikely to pull your content when the topic is queried.</p>
      <p><b>What to do:</b> Raise proximity by publishing topic-aligned content; watch
      the Proximity matrix and its confidence (real mention count) per row.</p>

      <h3>Feature C — Local Named Entity Recognition &amp; Knowledge Graphs</h3>
      <p><b>What it does:</b> spaCy extracts ORG/PRODUCT/PERSON entities; networkx
      builds a co-occurrence graph tracking how often competitors appear beside your
      topics vs how often your brand does.</p>
      <p><b>Why we analyze it:</b> Co-occurrence is the strongest signal a RAG corpus
      associates you with a topic. Absence = invisibility.</p>
      <p><b>What to do:</b> Earn co-mentions via guest posts, partnerships and
      citations on the high-density pages listed below.</p>

      <h3>Feature D — Unlinked Authority &amp; Citation Gap Finder</h3>
      <p><b>What it does:</b> Audits every article to classify your brand as
      linked, unlinked (mentioned, no link) or omitted while competitors are cited.</p>
      <p><b>Why we analyze it:</b> An unlinked or omitted mention is lost authority.
      The RAG Invisibility Index and Off-Page Targets turn this into a backlog.</p>
      <p><b>What to do:</b> Work the Off-Page Target list: secure links, convert
      unlinked mentions, and displace competitor-only citations.</p>

      <h3>Outputs you are looking at</h3>
      <p>KPI cards → corpus size, invisibility, share-of-voice. Proximity matrix →
      per-topic brand/competitor meaning overlap. Invisibility/SoV → per-topic gap.
      Link-vs-mention → citation health. Off-Page Targets → the link backlog.
      Provenance → every real URL behind the numbers. Recommendations → prioritized plan.</p>
    </div>
    """

    inv_index = cit["rag_invisibility_index"]
    sov = inv["composite_vector_share_of_voice_pct"]
    hw = data["meta"].get("harvest_warning")
    hw_banner = f"<div class='banner'>{_esc(hw)}</div>" if hw else ""

    # ---- advanced / enterprise sections -----------------------------
    adv = data.get("advanced", {}) or {}
    adv_html = _render_advanced(adv, brand, cfg, data.get("freshness") or {})

    # --- data-integrity / verification banner -----------------------
    integ = data["meta"].get("data_integrity", {}) or {}
    vscore = data["meta"].get("verification_score", 0.0)
    verified = data["meta"].get("verified", False)
    if verified:
        vclass, vlabel = "good", "VERIFIED"
    elif integ.get("models_real"):
        vclass, vlabel = "warn", "PARTIAL"
    else:
        vclass, vlabel = "critical", "UNVERIFIED"
    models = integ.get("embedding_model") or integ.get("embedding_kind", "?")
    ner = integ.get("ner_model") or integ.get("ner_kind", "?")
    support = integ.get("support_fraction", 0.0)
    verify_banner = (
        f"<div class='issue {vclass}' style='margin:18px 0 0;'>"
        f"<div class='issue-title'>Data Integrity: {vlabel} "
        f"(score {vscore}/100)</div>"
        f"<div class='issue-detail'>Models: {_esc(models)} embeddings / "
        f"{_esc(ner)} NER &nbsp;|&nbsp; Entities present in corpus: "
        f"{integ.get('entities_with_mentions',0)}/{integ.get('entities_total',0)} "
        f"({support*100:.0f}%) &nbsp;|&nbsp; Duplicates removed: "
        f"{integ.get('dedup_removed',0)} &nbsp;|&nbsp; Harvest OK: "
        f"{integ.get('harvest_ok')}.<br><b>Read this first:</b> scores are "
        f"real, model-derived estimates from the harvested corpus — verify "
        f"outreach targets manually. A low score means the run is not "
        f"trustworthy, not that the tool failed.</div></div>"
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RAG-EVDA Report — {_esc(brand)}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@600;700;800&display=swap');
:root{{
  --bg:#0b0e14; --bg2:#0e1320; --surface:#141a28; --surface2:#1b2233; --border:#28324c;
  --text:#e8ecf4; --muted:#94a3c4; --accent:#6d8bff; --accent2:#34d399; --accent3:#a78bfa;
  --good:#34d399; --warn:#fbbf24; --bad:#fb7185; --radius:16px;
  --shadow:0 12px 34px rgba(0,0,0,.45); --shadow-sm:0 4px 16px rgba(0,0,0,.30);
  --font:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --display:'Sora',var(--font);
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; color:var(--text); font-family:var(--font); font-size:14px; line-height:1.65;
  -webkit-font-smoothing:antialiased; letter-spacing:.1px;
  background:
    radial-gradient(1200px 640px at 10% -12%, rgba(109,139,255,.14), transparent 60%),
    radial-gradient(1000px 520px at 102% -4%, rgba(52,211,153,.10), transparent 55%),
    var(--bg); }}
.page {{ max-width:1240px; margin:0 auto; padding:0 22px 60px; }}
.brand {{ display:flex; gap:14px; align-items:flex-start; }}
.logo {{ width:46px; height:46px; border-radius:13px; flex:0 0 auto;
  background:linear-gradient(135deg,var(--accent),var(--accent2)); color:#06121f;
  font-family:var(--display); font-weight:800; font-size:17px; letter-spacing:-.5px;
  display:flex; align-items:center; justify-content:center; box-shadow:0 10px 24px rgba(52,211,153,.35); }}
header {{ padding:30px 0 20px; border-bottom:1px solid var(--border); margin-bottom:8px; }}
header h1 {{ margin:0; font-family:var(--display); font-size:24px; font-weight:800; letter-spacing:-.4px;
  background:linear-gradient(92deg,#cfe0ff,var(--accent) 42%,var(--accent2));
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }}
header .sub {{ color:var(--muted); margin-top:10px; font-size:13px; line-height:1.6; }}
h2 {{ display:flex; align-items:center; gap:9px; font-family:var(--display); font-size:18px; font-weight:700;
  color:var(--text); margin:32px 0 12px; letter-spacing:-.2px; }}
h2::before {{ content:""; width:4px; height:18px; border-radius:3px;
  background:linear-gradient(180deg,var(--accent),var(--accent2)); }}
section {{ margin:0; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin:18px 0; }}
.kpi {{ background:linear-gradient(180deg,var(--surface2),var(--surface));
  border:1px solid var(--border); border-radius:var(--radius); padding:18px 20px; box-shadow:var(--shadow-sm); }}
.kpi .v {{ font-family:var(--display); font-size:32px; font-weight:800; line-height:1.1; }}
.kpi .l {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.7px; margin-top:6px; }}
table {{ width:100%; border-collapse:separate; border-spacing:0; margin-top:10px;
  font-size:13px; background:var(--surface); border:1px solid var(--border);
  border-radius:var(--radius); overflow:hidden; }}
th,td {{ text-align:left; padding:11px 13px; border-bottom:1px solid var(--border); vertical-align:top; }}
th {{ color:var(--muted); text-transform:uppercase; font-size:10.5px; letter-spacing:.6px;
  background:var(--surface2); font-weight:600; }}
tbody tr:last-child td {{ border-bottom:none; }}
tbody tr:nth-child(even) {{ background:rgba(255,255,255,.02); }}
tbody tr:hover {{ background:rgba(109,139,255,.06); }}
.row-bad {{ background:rgba(251,113,133,.14) !important; }}
.row-warn {{ background:rgba(251,191,36,.12) !important; }}
.row-good {{ background:rgba(52,211,153,.12) !important; }}
.bartrack {{ position:relative; background:var(--bg); border:1px solid var(--border);
  border-radius:8px; height:18px; min-width:120px; display:inline-block; width:140px; }}
.bar {{ height:18px; border-radius:8px; background:linear-gradient(90deg,var(--accent),var(--accent2)); }}
.barval {{ position:absolute; right:7px; top:0; font-size:11px; line-height:18px; color:#fff; font-weight:600; }}
.src a, td a {{ color:#7fb4ff; text-decoration:none; }}
.src a:hover {{ text-decoration:underline; }}
.rel {{ color:var(--muted); font-size:11px; }}
.muted {{ color:var(--muted); }}
.conf {{ font-weight:700; padding:2px 8px; border-radius:6px; font-size:11px; }}
.conf-high {{ color:var(--good); background:rgba(52,211,153,.14); }}
.conf-medium {{ color:var(--warn); background:rgba(251,191,36,.14); }}
.conf-low {{ color:#e3a857; background:rgba(227,168,87,.14); }}
.conf-none {{ color:var(--bad); background:rgba(251,113,133,.14); }}
.banner {{ margin:18px 0 0; padding:14px 18px; border-radius:var(--radius);
  background:rgba(251,113,133,.14); border:1px solid var(--bad); color:#ffd9dd; font-size:13px; }}
.issues {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; margin-top:12px; }}
.issue {{ border-radius:var(--radius); padding:14px 17px; background:var(--surface);
  border:1px solid var(--border); border-left:4px solid #888; box-shadow:var(--shadow-sm); }}
.issue.critical {{ background:rgba(251,113,133,.10); border-left-color:var(--bad); }}
.issue.warn {{ background:rgba(251,191,36,.08); border-left-color:var(--warn); }}
.issue.info {{ background:rgba(109,139,255,.08); border-left-color:var(--accent); }}
.issue.good {{ background:rgba(52,211,153,.08); border-left-color:var(--good); }}
.issue-title {{ font-weight:700; font-size:14px; margin-bottom:4px; }}
.issue-detail {{ font-size:12.5px; color:#c9d3ea; line-height:1.6; }}
.rec {{ background:linear-gradient(180deg,var(--surface),var(--bg2)); border:1px solid var(--border);
  border-left:4px solid var(--accent); border-radius:var(--radius);
  padding:14px 18px; margin:12px 0; box-shadow:var(--shadow-sm); }}
.rec.p1 {{ border-left-color:var(--bad); }}
.rec.p2 {{ border-left-color:var(--warn); }}
.rec.p3 {{ border-left-color:var(--accent); }}
.rec-head {{ font-size:14px; font-weight:600; }}
.badge {{ background:linear-gradient(92deg,var(--accent),var(--accent2)); color:#06121f; border-radius:7px; padding:2px 9px;
  font-size:11px; font-weight:800; }}
.cat {{ color:var(--muted); font-size:11px; }}
.rec-body {{ color:#c9d3ea; margin:7px 0; font-size:13px; line-height:1.6; }}
.rec-action {{ font-size:13px; color:#7ee2a8; }}
.method {{ background:var(--surface); border:1px solid var(--border);
  border-radius:var(--radius); padding:10px 24px 20px; }}
.method h3 {{ color:#7fb4ff; font-size:14px; margin:16px 0 4px; }}
.method p {{ margin:5px 0; font-size:13px; color:#c9d3ea; line-height:1.6; }}
.method b {{ color:var(--text); }}
.footer {{ padding:22px 0; color:var(--muted); font-size:12.5px; line-height:1.6;
  border-top:1px solid var(--border); margin-top:24px; }}
details {{ margin-top:6px; }}
summary {{ cursor:pointer; color:#7fb4ff; font-size:13px; padding:8px 0; }}
body.light {{ --bg:#f5f8fc; --bg2:#ffffff; --surface:#ffffff; --surface2:#eef2f8; --border:#dde4ef;
  --text:#0f172a; --muted:#5b6b86; --shadow:0 12px 34px rgba(20,40,80,.10);
  --shadow-sm:0 4px 16px rgba(20,40,80,.08); }}
body.light header h1 {{ background:linear-gradient(92deg,#1e3a8a,var(--accent) 46%,#0f766e);
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }}
body.light .kpi, body.light table, body.light .issue, body.light .rec {{ box-shadow:var(--shadow-sm); }}
</style></head>
<body><div class="page">
<header>
  <div class="brand">
    <div class="logo">EV</div>
    <div>
      <h1>RAG Corpus Entity &amp; Vector Distance Auditor</h1>
      <div class="sub">Target brand: <b>{_esc(brand)}</b> &nbsp;|&nbsp;
      Topics: {_esc(', '.join(cfg['industry_topics']))} &nbsp;|&nbsp;
      Competitors: {_esc(', '.join(cfg['competitor_entities']))} &nbsp;|&nbsp;
      Docs: {ctx_stats.get('doc_count',0)} &nbsp;|&nbsp;
      Embedding: {_esc(data['meta']['embedding_kind'])}</div>
    </div>
  </div>
</header>
{hw_banner}
{verify_banner}

<div class="kpis">
  <div class="kpi"><div class="v" style="color:#e67e22">{inv_index}%</div>
    <div class="l">RAG Invisibility Index</div></div>
  <div class="kpi"><div class="v" style="color:#1abc9c">{sov}%</div>
    <div class="l">Vector Share of Voice</div></div>
  <div class="kpi"><div class="v">{ctx_stats.get('doc_count',0)}</div>
    <div class="l">Retrieval Corpus Docs</div></div>
  <div class="kpi"><div class="v">{len(cit['off_page_targets'])}</div>
    <div class="l">Off-Page Targets</div></div>
  <div class="kpi"><div class="v">{len(recs)}</div>
    <div class="l">Recommendations</div></div>
</div>

<section><h2>⚠ Brand Health Issues — What You're Lacking</h2>
<div class="issues">{issue_cards}</div></section>

<section><h2>Semantic Vector Proximity (0.0–1.0)</h2>
<table><thead><tr><th>Topic</th><th>Entity</th><th>Proximity</th>
<th>Label</th><th>#High-Rel Docs</th><th>Support (mentions)</th>
<th>Confidence</th><th>Top Real Sources</th></tr></thead>
<tbody>{prox_rows}</tbody></table>
<div class="footer">Confidence = how many real corpus mentions back the score
(high ≥ {cfg['confidence_min_support']} mentions). Low/none = the entity was rarely
present in the harvested corpus, so interpret with care. Red rows = brand is
semantically "Far" from that topic.</div>
</section>

<section><h2>Per-Topic RAG Invisibility &amp; Share of Voice</h2>
<table><thead><tr><th>Topic</th><th>Rel. Docs</th><th>Brand Present</th>
<th>Competitor Present</th><th>Vector SoV %</th><th>Invisibility %</th><th>Threshold</th></tr></thead>
<tbody>{inv_rows}</tbody></table>
<div class="footer">"Threshold" is the auto-calibrated per-topic relevance cut
(80th percentile of the harvested corpus similarity), so the metric tracks real
signal instead of a fixed 0.70. Red = ≥50% invisible, amber = ≥25%.</div>
</section>

<section><h2>Entity Link vs. Mention Audit</h2>
<table><thead><tr><th>Entity</th><th>Mentioned / Total</th><th>Linked</th>
<th>Unlinked</th><th>Omitted</th><th>Mention Rate</th><th>Link Rate</th></tr></thead>
<tbody>{ent_rows}</tbody></table>
<div class="footer">Red rows = your brand is omitted from ≥50% of articles that cite competitors.</div></section>

<section><h2>High-Density Off-Page Target List</h2>
<table><thead><tr><th>#</th><th>URL</th><th>Source</th><th>Top Topic</th>
<th>Relevance</th><th>Competitors Present</th></tr></thead>
<tbody>{tgt_rows}</tbody></table></section>

<section><h2>Data Provenance — Harvested Sources</h2>
<table><thead><tr><th>#</th><th>Source</th><th>Type</th><th>Top Topic</th>
<th>Relevance</th><th>Chars</th><th>HTTP</th><th>URL</th></tr></thead>
<tbody>{prov_rows}</tbody></table>
<div class="footer">Every metric above is computed from these real, locally-harvested
web documents. "HTTP" = the status code of the live fetch (200 = verified retrieved;
green rows are confirmed live pages). "Relevance" = cosine similarity to each
document's most relevant topic (vs its auto-calibrated threshold). Content hashes and
final URLs are stored in <code>sources.csv</code> / <code>report.json</code> so any
number can be independently audited.</div>
</section>

<section><h2>Prioritized Recommendations</h2>{rec_html}</section>

{adv_html}

<section><h2>How the Tool Works — Methodology</h2>
<details open><summary>Show / hide the four micro-engines &amp; what to do</summary>
{methodology}</details></section>

<div class="footer">{harvest_line}<br>
Generated by RAG-EVDA — local, zero-cost vector intelligence. Scores are
model-derived estimates; verify outreach manually.</div>
</div></body></html>"""
    return html_doc


def write_dashboard(path: str, data: Dict[str, Any]) -> str:
    out = render_dashboard(data)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(out)
    logger.info("wrote HTML dashboard: %s", path)
    return path
