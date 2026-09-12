"""Shared issue-detection framework for analysis pages and the PDF.

Every rule reads the real computed ``data`` dict — nothing is invented. Each
issue carries a severity (critical / high / medium / good), the engine key it
belongs to (matching deep_analysis._DISPATCH, or None for run-global issues),
a short bold title and a one-line evidence detail.

Both the web analysis (colored alert cards) and the enterprise PDF (tinted
callout boxes) render from this single source so they can never disagree.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "good": 3}

# Engine keys mirror deep_analysis._DISPATCH. Poisoning / engine-matrix have no
# dedicated page, so they attach to the closest engine section.
ENGINE_LABELS = {
    "web_harvester": "Engine 1 · Harvester",
    "vector_embedding": "Engine 2 · Embeddings",
    "ner_graphs": "Engine 3 · NER Graphs",
    "citation_gap": "Engine 4 · Citation Gaps",
    "chunking": "Engine 5 · Chunking",
    "drift_tracking": "Engine 6 · Drift",
    "llm_analysis": "Engine 7 · LLM Briefs",
    "sentiment": "Engine 8 · Sentiment",
    "synthetic_queries": "Engine 9 · Synthetic Queries",
    "token_density": "Engine 10 · Token Density",
}


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


def collect_issues(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scan the full audit output and return severity-ranked issues."""
    issues: List[Dict[str, Any]] = []
    meta = data.get("meta", {}) or {}
    cfg = meta.get("config", {}) or {}
    di = meta.get("data_integrity", {}) or {}
    brand = str(cfg.get("target_brand", "") or "")
    brand_l = brand.lower()

    cite = data.get("citation_gap", {}) or {}
    inv = data.get("invisibility", {}) or {}
    rows = (data.get("proximity", {}) or {}).get("rows", []) or []
    ent_sum = cite.get("entity_summary", []) or []
    adv = data.get("advanced", {}) or {}

    def add(sev: str, engine: str | None, title: str, detail: str) -> None:
        issues.append({"sev": sev, "engine": engine, "title": title, "detail": detail})

    # ---- harvest integrity -------------------------------------------------
    if not di.get("harvest_ok"):
        add("high", "web_harvester", "Harvest degraded — evidence is thin",
            f"Only {di.get('harvested_docs', 0)} documents harvested. "
            "Scores below carry wider uncertainty; re-run with higher crawl depth.")
    if not di.get("provenance_complete"):
        add("medium", "web_harvester", "Provenance partially complete",
            "Some sources lack full fetch metadata. Raw URLs remain in report.json.")

    # ---- invisibility (the headline metric) --------------------------------
    comp_inv = _f(inv.get("composite_invisibility_index_pct"))
    if comp_inv is not None:
        if comp_inv >= 60:
            add("critical", "citation_gap",
                f"Brand invisible in {comp_inv:.1f}% of relevant passages",
                "A majority of high-ranking industry content omits the brand while "
                "citing rivals — top-priority content-gap crisis.")
        elif comp_inv >= 35:
            add("high", "citation_gap",
                f"Brand invisible in {comp_inv:.1f}% of relevant passages",
                "More than a third of relevant content excludes the brand. "
                "Attack the blind-spot topics in §13 first.")
        elif comp_inv <= 20:
            add("good", "citation_gap",
                f"Strong presence — only {comp_inv:.1f}% composite invisibility",
                "The brand holds its ground. Defend with drift-tracked schedules.")
    per_topic = inv.get("per_topic", []) or []
    blind = sorted(
        [t for t in per_topic if (_f(t.get("topic_invisibility_pct")) or 0) >= 70],
        key=lambda t: float(t.get("topic_invisibility_pct") or 0), reverse=True)[:5]
    for t in blind:
        add("critical", "citation_gap",
            f"Blind spot: “{t.get('topic')}” {float(t.get('topic_invisibility_pct') or 0):.1f}% invisible",
            f"{t.get('brand_present_docs', 0)}/{t.get('relevant_docs', 0)} docs mention the brand vs "
            f"{t.get('competitor_present_docs', 0)} citing rivals.")
    weak = sorted(
        [t for t in per_topic
         if 40 <= (_f(t.get("topic_invisibility_pct")) or 0) < 70],
        key=lambda t: float(t.get("topic_invisibility_pct") or 0), reverse=True)[:5]
    for t in weak:
        add("high", "citation_gap",
            f"Weak topic: “{t.get('topic')}” {float(t.get('topic_invisibility_pct') or 0):.1f}% invisible",
            f"Rivals present in {t.get('competitor_present_docs', 0)} docs; "
            f"brand in {t.get('brand_present_docs', 0)}.")

    # ---- proximity ----------------------------------------------------------
    brand_rows = [r for r in rows if str(r.get("entity", "")).lower() == brand_l]
    far_rows = [r for r in brand_rows
                if "far" in str(r.get("label", "")).lower()
                or "unrelated" in str(r.get("label", "")).lower()][:4]
    for r in far_rows:
        add("high", "vector_embedding",
            f"Semantically distant: brand ↔ “{r.get('topic')}” ({float(r.get('proximity') or 0):.3f})",
            "The retriever sees the brand as unrelated to this topic. "
            "Needs co-occurrence content pairing brand + topic terms.")
    means = [_f(r.get("proximity")) for r in brand_rows]
    means = [m for m in means if m is not None]
    if means and statistics.mean(means) < 0.35:
        add("high", "vector_embedding",
            f"Brand mean proximity only {statistics.mean(means):.3f}",
            "Across all topics the brand sits far from industry centroids. "
            "Systematic topical authority work required.")
    # closest rival
    agg: Dict[str, List[float]] = {}
    for r in rows:
        v = _f(r.get("proximity"))
        if v is not None:
            agg.setdefault(str(r.get("entity", "")), []).append(v)
    lead = sorted(((e, statistics.mean(v)) for e, v in agg.items() if v),
                  key=lambda x: -x[1])
    rival = next((x for x in lead if x[0].lower() != brand_l), None)
    brand_mean = statistics.mean(agg.get(brand, []) or
                                 next((v for e, v in agg.items() if e.lower() == brand_l), [])) \
        if any(e.lower() == brand_l for e in agg) else None
    if rival and brand_mean is not None and rival[1] - brand_mean > 0.10:
        add("high", "vector_embedding",
            f"“{rival[0]}” outranks the brand by {rival[1] - brand_mean:.3f} mean proximity",
            f"Rival {rival[1]:.3f} vs brand {brand_mean:.3f}. Displacement content "
            "must close this exact gap topic by topic.")

    # ---- citation ledger ------------------------------------------------------
    for e in ent_sum:
        if str(e.get("entity", "")).lower() != brand_l:
            continue
        unl = int(e.get("docs_unlinked", 0) or 0)
        om = int(e.get("docs_omitted", 0) or 0)
        tot = int(e.get("docs_total", 0) or 1)
        if unl > 0:
            add("high", "citation_gap",
                f"{unl} unlinked brand mentions — instant outreach wins",
                "These pages already name the brand but link elsewhere. "
                "Request citation links; highest ROI action in this report.")
        if om / max(1, tot) >= 0.70:
            add("high", "citation_gap",
                f"Brand omitted from {om}/{tot} audited documents",
                "Structural citation gap. Pitch data-led stories to the off-page "
                "target list, top-down.")
        break

    # ---- sentiment / hallucination ---------------------------------------------
    sent = adv.get("sentiment", {}) or {}
    per_ent = sent.get("per_entity", []) or []
    brand_sent = next((s for s in per_ent if str(s.get("entity", "")).lower() == brand_l), None)
    if brand_sent and (_f(brand_sent.get("net_sentiment")) or 0) < 0:
        add("critical", "sentiment",
            f"Brand net sentiment is negative ({float(brand_sent.get('net_sentiment') or 0):.3f})",
            "Retrieved windows frame the brand hostilely. Neutralization content "
            "is urgent — see verbatim risk windows.")
    risky = sorted([s for s in per_ent if int(s.get("risk_windows", 0) or 0) > 0],
                   key=lambda s: int(s.get("risk_windows", 0) or 0), reverse=True)[:4]
    for s in risky:
        if str(s.get("entity", "")).lower() == brand_l:
            add("critical", "sentiment",
                f"{s.get('risk_windows')} hostile retrieval windows name the brand",
                "Quoted verbatim in §9. Each one can surface inside an AI answer.")
        else:
            add("medium", "sentiment",
                f"Negative framing around “{s.get('entity')}” ({s.get('risk_windows')} windows)",
                "Rival-adjacent toxicity can bleed onto shared topics. Monitor.")

    # ---- drift -------------------------------------------------------------------
    alerts = (adv.get("drift", {}) or {}).get("alerts", []) or []
    for a in alerts[:5]:
        add("high", "drift_tracking",
            f"Drift alert: {a.get('topic', 'a topic')} moved",
            str(a.get("message", a.get("detail", "")))[:160])

    # ---- LLM ------------------------------------------------------------------------
    llm = adv.get("llm", {}) or {}
    if not llm.get("available"):
        add("medium", "llm_analysis", "Local LLM briefs unavailable",
            "Ollama was unreachable, so free-text gap rationale is omitted. "
            "All deterministic metrics are complete; start Ollama for narrative briefs.")

    # ---- synthetic --------------------------------------------------------------------
    syn = adv.get("synthetic_queries", {}) or {}
    if not syn.get("per_entity"):
        add("medium", "synthetic_queries", "No synthetic retrieval prompts generated",
            "Thin corpus for reverse-engineering. Grow crawl depth, then re-run.")

    # ---- token density ------------------------------------------------------------------
    td = adv.get("token_density", {}) or {}
    gap_topics = sorted(
        [t for t in (td.get("per_topic", []) or [])
         if (_f(t.get("tokens_needed_to_displace")) or 0) >= 30],
        key=lambda t: float(t.get("tokens_needed_to_displace") or 0), reverse=True)[:3]
    for t in gap_topics:
        add("medium", "token_density",
            f"“{t.get('topic')}” needs {t.get('tokens_needed_to_displace')} on-window tokens to displace "
            f"“{t.get('leading_competitor')}”",
            "Largest content investment in this run. Follow the displacement action verbatim.")

    # ---- poisoning -------------------------------------------------------------------------
    pois = adv.get("poisoning", {}) or {}
    status = str(pois.get("brand_poisoning_status", "clean") or "clean")
    if status.lower() not in ("clean", "none", ""):
        add("critical", "citation_gap",
            f"Vector-poisoning signal on the brand: {status}",
            f"{pois.get('toxic_source_count', 0)} toxic co-citing sources detected. "
            "Disavow / outrank before the centroid drag compounds.")
    elif int(pois.get("toxic_source_count", 0) or 0) > 0:
        add("high", "citation_gap",
            f"{pois.get('toxic_source_count')} toxic sources co-cite entities in this space",
            "Not yet dragging the brand centroid, but monitor per §12.")

    # ---- engine matrix -------------------------------------------------------------------------
    em = adv.get("engine_matrix", {}) or {}
    ecomp = em.get("engine_composite", []) or []
    if ecomp:
        weakest = min(ecomp, key=lambda r: float(r.get("composite_sov_pct") or 100))
        if (_f(weakest.get("composite_sov_pct")) or 100) < 25:
            add("medium", "vector_embedding",
                f"Weakest AI surface: {weakest.get('engine')} "
                f"({float(weakest.get('composite_sov_pct') or 0):.1f}% SoV)",
                "Platform-specific formatting (feeds, schema, Q&A blocks) needed for this engine.")

    # ---- verification ------------------------------------------------------------------------------
    if not di.get("verified"):
        add("medium", None, "Verification is PARTIAL, not VERIFIED",
            f"Score {_r(di.get('verification_score'))}/100. Check §4 sub-scores "
            "before presenting externally.")
    return sorted(issues, key=lambda i: (SEV_ORDER.get(i["sev"], 9), i["title"]))


def _r(x: Any, nd: int = 1) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "—"


SEV_LABEL = {"critical": "CRITICAL", "high": "HIGH RISK", "medium": "WATCH", "good": "STRENGTH"}


def _esc(s: Any) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def banner_html(issues: List[Dict[str, Any]], engine: str | None = None,
                limit: int = 6, title: str = "") -> str:
    """Colored alert cards for the web UI. engine=None renders run-global top issues."""
    sel = [i for i in issues if (i.get("engine") == engine if engine else i.get("engine") is None)]
    if engine is None:
        # global strip: top issues across all engines
        sel = issues[:limit]
    else:
        sel = sel[:limit]
    if not sel:
        return ""
    head = title or ("⚠ Issues needing attention" if not engine
                     else f"⚠ Issues in {ENGINE_LABELS.get(engine, 'this engine')}")
    cards = "".join(
        f'<div class="iss iss-{i["sev"]}"><span class="sev sev-{i["sev"]}">'
        f'{SEV_LABEL.get(i["sev"], i["sev"].upper())}</span>'
        f'<div class="iss-body"><b>{_esc(i["title"])}</b>'
        f'<span>{_esc(i["detail"])}'
        + (f' <span class="muted">· {ENGINE_LABELS.get(i["engine"], "")}</span>'
           if not engine and i.get("engine") else "")
        + "</span></div></div>"
        for i in sel
    )
    n_more = (len(issues if not engine else
                   [i for i in issues if i.get("engine") == engine]) - len(sel))
    more = f'<div class="muted" style="font-size:12px">+ {n_more} further findings below.</div>' \
        if n_more > 0 else ""
    return (f'<div class="iss-wrap" style="margin:14px 0 4px">'
            f'<div class="iss-head">{head} <span class="iss-count">{len(sel)}</span></div>'
            f"{cards}{more}</div>")


def summary_strip_html(issues: List[Dict[str, Any]]) -> str:
    """Compact severity counts for the top of Step-2."""
    counts = {"critical": 0, "high": 0, "medium": 0, "good": 0}
    for i in issues:
        if i["sev"] in counts:
            counts[i["sev"]] += 1
    return (
        '<div class="m3-chip-row" style="margin:10px 0 2px">'
        f'<span class="m3-chip"><b style="color:var(--m3-error)">{counts["critical"]}</b>&nbsp;critical</span>'
        f'<span class="m3-chip"><b style="color:var(--m3-error)">{counts["high"]}</b>&nbsp;high-risk</span>'
        f'<span class="m3-chip"><b>{counts["medium"]}</b>&nbsp;to watch</span>'
        f'<span class="m3-chip"><b>{counts["good"]}</b>&nbsp;strengths</span>'
        "</div>"
    )
