"""Deep-dive analysis pages for each of the 10 core micro-engines.

Every function receives the full ``report.json`` data dict and renders a
comprehensive HTML page showing the real computed output, intermediate data,
and methodology for that specific engine. All data is sourced directly from
the report — no fabrication.
"""

from __future__ import annotations

from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(s: Any) -> str:
    if s is None:
        return "&mdash;"
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _pct(x: Any, nd: int = 1) -> str:
    """Fraction 0..1 -> percent. Already-percent values pass through."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "&mdash;"
    if v > 1.5:
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


def _brand_l(cfg: Dict) -> str:
    return str(cfg.get("target_brand", "") or "").lower()


def _num_or_none(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _classes_for_prox(rows: List[Dict], brand: str) -> List[str]:
    """Brand far/unrelated rows glow amber; tightly-bound brand rows glow green."""
    out = []
    for r in rows:
        lab = str(r.get("label", "")).lower()
        if str(r.get("entity", "")).lower() == brand and brand:
            if "far" in lab or "unrelated" in lab:
                out.append("row-high")
            elif "tight" in lab:
                out.append("row-good")
            else:
                out.append("")
        else:
            out.append("")
    return out


def _classes_for_gap(gaps: List[Dict]) -> List[str]:
    out = []
    for g in gaps:
        sev = str(g.get("severity", "")).lower()
        out.append("row-critical" if "critical" in sev else
                   ("row-high" if "high" in sev else ""))
    return out


def _classes_for_inv(per_topic: List[Dict]) -> List[str]:
    out = []
    for t in per_topic:
        v = _num_or_none(t.get("topic_invisibility_pct")) or 0
        out.append("row-critical" if v >= 70 else ("row-high" if v >= 40 else ""))
    return out


def _classes_for_ledger(ent_sum: List[Dict], brand: str) -> List[str]:
    out = []
    for e in ent_sum:
        if str(e.get("entity", "")).lower() == brand and brand:
            tot = int(e.get("docs_total", 0) or 0) or 1
            om = int(e.get("docs_omitted", 0) or 0)
            unl = int(e.get("docs_unlinked", 0) or 0)
            out.append("row-high" if (om / tot >= 0.7 or unl > 0) else "")
        else:
            out.append("")
    return out


def _classes_for_sent(per_entity: List[Dict]) -> List[str]:
    out = []
    for e in per_entity:
        risks = int(e.get("risk_windows", 0) or 0)
        net = _num_or_none(e.get("net_sentiment"))
        if risks > 0 or (net is not None and net < 0):
            out.append("row-critical")
        elif "negative" in str(e.get("framing", "")).lower():
            out.append("row-high")
        else:
            out.append("")
    return out


def _classes_for_drift(per_topic: List[Dict]) -> List[str]:
    return ["row-high" if t.get("anomaly") else "" for t in per_topic]


def _classes_for_density(per_topic: List[Dict]) -> List[str]:
    out = []
    for t in per_topic:
        sev = str(t.get("severity", "")).lower()
        need = _num_or_none(t.get("tokens_needed_to_displace")) or 0
        out.append("row-critical" if "critical" in sev else
                   ("row-high" if ("high" in sev or need >= 30) else ""))
    return out


def _classes_for_recs(recs: List[Dict]) -> List[str]:
    out = []
    for r in recs:
        pri = str(r.get("priority", "")).lower()
        out.append("row-critical" if ("p0" in pri or "critical" in pri) else
                   ("row-high" if ("p1" in pri or "high" in pri) else ""))
    return out


def _bar(pct_val: float, width: int = 120) -> str:
    """Render a small colored bar for a percentage."""
    p = max(0, min(100, float(pct_val or 0)))
    color = "var(--m3-tertiary)" if p > 60 else ("var(--m3-primary)" if p > 30 else "var(--m3-error)")
    return (f'<div style="display:inline-block;background:var(--m3-surface-container-high);'
            f'border-radius:6px;width:{width}px;height:12px;overflow:hidden;vertical-align:middle">'
            f'<div style="width:{p:.0f}%;height:100%;background:{color};border-radius:6px"></div></div>'
            f' <span style="font-size:11px;color:var(--m3-on-surface-variant)">{p:.1f}%</span>')


def _t(rows: List[List[str]], cls: str = "m3-table",
       row_classes: List[str] | None = None) -> str:
    """Render a <table> from header + data rows. First row = header.

    ``row_classes`` optionally holds one CSS class per body row (e.g.
    "row-critical" / "row-high" / "row-good") so problem rows are boldly
    highlighted in both dark and light modes.
    """
    if not rows:
        return "<p class='muted'>No data.</p>"
    hdr = rows[0]
    body_rows = rows[1:]
    ths = "".join(f"<th>{c}</th>" for c in hdr)
    trs = ""
    for idx, r in enumerate(body_rows):
        tds = "".join(f"<td>{c}</td>" for c in r)
        rc = (row_classes[idx] if row_classes and idx < len(row_classes)
              and row_classes[idx] else "")
        trs += f"<tr class='{rc}'>{tds}</tr>" if rc else f"<tr>{tds}</tr>"
    return f'<table class="{cls}"><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>'


def _nav(job_id: str, current: str) -> str:
    """Tab navigation bar across all 10 feature pages."""
    features = [
        ("1", "web_harvester", "Web Harvester"),
        ("2", "vector_embedding", "Vector Embedding"),
        ("3", "ner_graphs", "NER &amp; Graphs"),
        ("4", "citation_gap", "Citation Gap"),
        ("5", "chunking", "RAG Chunking"),
        ("6", "drift_tracking", "Drift Tracking"),
        ("7", "llm_analysis", "LLM Analysis"),
        ("8", "sentiment", "Sentiment Audit"),
        ("9", "synthetic_queries", "Synthetic Queries"),
        ("10", "token_density", "Token Density"),
    ]
    tabs = ""
    for num, key, label in features:
        active = "style='border-color:var(--m3-primary);color:var(--m3-on-surface)'" if key == current else ""
        tabs += (f'<a href="/page/deep/{job_id}/{key}" {active}>'
                 f'<span style="font-weight:800;margin-right:4px">{num}</span>{label}</a>')
    return f'<div class="topnav" style="margin-bottom:20px">{tabs}</div>'


def _wrap(job_id: str, current: str, title: str, body: str) -> str:
    """Wrap content in a full page with navigation."""
    return (
        f'<h2 class="m3-h2">{title}</h2>'
        f'{_nav(job_id, current)}'
        f'{body}'
    )


def _engine_banner(data: Dict, engine: str) -> str:
    """Bold color-coded issue cards for one engine (empty when all clear)."""
    try:
        from . import issues as _issues
        return _issues.banner_html(_issues.collect_issues(data), engine=engine)
    except Exception:  # noqa: BLE001 — highlighting must never break a page
        return ""


# ---------------------------------------------------------------------------
# 1) Web Harvester — full detail
# ---------------------------------------------------------------------------

def web_harvester(data: Dict, job_id: str) -> str:
    meta = data.get("meta", {}) or {}
    cfg = meta.get("config", {}) or {}
    hs = meta.get("harvest_stats", {}) or {}
    di = meta.get("data_integrity", {}) or {}
    # Real provenance: top-level `provenance` list (v1.1) or freshness per_source.
    # Never fabricate status/freshness — read recorded HTTP fields verbatim.
    provenance = data.get("provenance", []) or []
    if not provenance:
        provenance = (data.get("freshness", {}) or {}).get("per_source", []) or []
    # Fallback only when provenance truly absent (legacy jobs): show off-page
    # targets explicitly labelled as partial, with honestly-unknown fields.
    citation_gap = data.get("citation_gap", {}) or {}
    off_page = citation_gap.get("off_page_targets", []) or []

    # Get all sources from the proximity/citation data
    sources_table = [["doc_id", "URL", "Title", "Source", "Domain", "Topic", "Relevance", "Chars", "Status", "Freshness", "Age (days)", "Fetch (ms)", "Live"]]
    if provenance:
        for s in provenance:
            url = s.get("url", "") or ""
            domain = s.get("domain", "") or (url.split("/")[2] if "://" in url else "")
            sources_table.append([
                _esc(s.get("doc_id", "")),
                f"<a href='{_esc(url)}' target='_blank'>{_esc(url[:80])}</a>",
                _esc(s.get("title", "")),
                _esc(s.get("source_type", "")),
                _esc(domain),
                _esc(s.get("top_topic", s.get("max_topic", ""))),
                _round(s.get("topic_relevance", s.get("max_topic_sim"))),
                _num(s.get("chars", s.get("text_chars", ""))),
                _esc(s.get("http_status", "")),
                _esc(s.get("staleness", "")),
                _esc(s.get("age_days", "")),
                _esc(s.get("fetch_latency_ms", s.get("fetch_ms", ""))),
                _esc(s.get("live", "")),
            ])
    else:
        for t in off_page:
            url = t.get("url", "")
            sources_table.append([
                "",
                f"<a href='{_esc(url)}' target='_blank'>{_esc(url[:80])}</a>",
                _esc(t.get("title", "")),
                _esc(t.get("source_type", "")),
                _esc(url.split("/")[2] if "/" in url else ""),
                _esc(t.get("top_topic", "")),
                _round(t.get("topic_relevance")),
                "",
                "unknown",
                "unknown",
                "unknown",
                "unknown",
                "unknown",
            ])

    # Also from the recommendation URLs (kept for link integrity, not duplicated
    # into the sources table — sources_table above already holds real provenance).
    # NOTE: legacy hardcoded "200/fresh/0/True" rows were removed: they fabricated
    # provenance for off-page targets. Unknown fields now render as "unknown".

    harvest_detail = f"""
    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Harvest Configuration</h3>
      {_t([
        ["Parameter", "Value", "Description"],
        ["Harvester engine", _esc(cfg.get("harvester", "")),
         "Primary search backend (duckduckgo / searxng / file)"],
        ["Locality", _esc(cfg.get("locality") or "global"),
         "Geographic region code for localized search results"],
        ["Crawl depth", _num(cfg.get("crawl_depth", 50)),
         "Max pages to fetch per search query"],
        ["Max pages", _num(cfg.get("max_pages", 200)),
         "Hard ceiling on total pages fetched across all queries"],
        ["Max concurrency", _num(cfg.get("max_concurrency", 8)),
         "Parallel HTTP fetch threads for throughput"],
        ["Request timeout", f'{cfg.get("request_timeout", 20)}s',
         "Per-page fetch timeout before skip"],
        ["User agent", _esc(cfg.get("user_agent", "")[:60]) + "...",
         "HTTP User-Agent string sent to targets"],
        ["Include Reddit", "Yes" if cfg.get("include_reddit") else "No",
         "Whether Reddit threads are included in harvest scope"],
        ["Include news", "Yes" if cfg.get("include_news") else "No",
         "Whether news articles are included in harvest scope"],
        ["Proxy", _esc(cfg.get("proxy") or "none"),
         "Optional HTTP proxy for anonymised fetching"],
        ["SearXNG base URL", _esc(cfg.get("searxng_base_url") or "not configured"),
         "Self-hosted SearXNG instance URL (if preferred)"],
        ["Prefer SearXNG", "Yes" if cfg.get("prefer_searxng") else "No",
         "Use SearXNG as primary when both are available"],
      ])}
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Harvest Pipeline — Step by Step</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant)">
        <p><b>Step 1: Query Generation.</b> For each of the <b>{_num(len(cfg.get('industry_topics', [])))}</b>
        configured industry topics, the engine generates search queries targeting
        <b>{_esc(cfg.get('search_intent', 'informational'))}</b> intent.
        Queries use template patterns like "best {{topic}} options" or "{{brand}} vs alternatives"
        plus the configured SERP footprints.</p>

        <p><b>Step 2: DuckDuckGo API Search.</b> The <code>ddgs</code> library sends
        <b>{_num(hs.get('queries', 0))}</b> search queries to DuckDuckGo's API,
        returning <b>{_num(hs.get('candidates', 0))}</b> candidate URLs
        ({_num(hs.get('empty_queries', 0))} empty queries filtered out).</p>

        <p><b>Step 3: Candidate Deduplication.</b> Near-duplicate URLs (similarity &gt;
        {_num(cfg.get('near_dup_threshold', 0.95))}) are removed. Content-hash
        deduplication catches the same article served from multiple URLs.
        <b>{_num(di.get('dedup_removed', 0))}</b> duplicates were removed.</p>

        <p><b>Step 4: Live HTTP Fetch.</b> Each candidate is fetched with real HTTP
        requests using <code>httpx</code>. Pages returning non-200 status codes
        (403, 404, 401, etc.) are logged and skipped. Average fetch latency is
        captured per-source for freshness validation.</p>

        <p><b>Step 5: HTML Cleanroom Parsing.</b> Fetched HTML passes through
        <code>trafilatura</code> + <code>BeautifulSoup</code> to strip navigation
        bars, footers, sidebars, advertisements, cookie banners and all non-content
        boilerplate. Only the pure body text that a RAG crawler would actually
        ingest is retained. This is the exact text a real AI search engine processes.</p>

        <p><b>Step 6: Content Validation.</b> Cleaned text shorter than
        {cfg.get('min_paragraph_chars', 40)} characters is discarded. Duplicate
        content hashes are removed. The result is <b>{_num(hs.get('fetched', 0))}</b>
        clean, indexable documents forming the audit corpus.</p>

        <p><b>Step 7: Feed &amp; Footprint Augmentation.</b> If RSS/Atom feeds or
        SERP footprints are configured, additional documents are ingested from
        those sources and merged into the corpus with deduplication.</p>

        <p><b>Step 8: Local Corpus Integration.</b> If local ground-truth documents
        (PDFs, Markdown, text files) are provided, they are parsed and merged
        into the corpus for internal-vs-web vector comparison.</p>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Harvest Statistics</h3>
      {_t([
        ["Metric", "Value", "Explanation"],
        ["Search queries executed", _num(hs.get("queries", 0)),
         "Total DuckDuckGo / SearXNG API calls"],
        ["Empty queries (no results)", _num(hs.get("empty_queries", 0)),
         "Queries that returned zero candidate URLs"],
        ["Raw candidate URLs", _num(hs.get("candidates", 0)),
         "URLs returned before dedup and fetch filtering"],
        ["Pages successfully fetched", _num(hs.get("fetched", 0)),
         "Pages returning HTTP 200 with valid HTML content"],
        ["Near-duplicates removed", _num(di.get("dedup_removed", 0)),
         "URLs/content hashes caught by deduplication"],
        ["Final clean documents", _num(meta.get("context_stats", {}).get("doc_count", 0)),
         "Documents entering the vector analysis pipeline"],
        ["Harvest OK", "Yes" if di.get("harvest_ok") else "No",
         "Whether harvest produced a valid corpus"],
        ["Source types", "web, news, reddit, file",
         "Content-type classification of harvested sources"],
      ])}
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">All Harvested Sources ({_num(len(off_page))} shown)</h3>
      {_t(sources_table)}
    </div>
    """

    return _wrap(job_id, "web_harvester",
                 "Engine 1: Zero-Cost Headless Web Harvester — Full Analysis",
                 _engine_banner(data, "web_harvester") + harvest_detail)


# ---------------------------------------------------------------------------
# 2) Vector Embedding & Semantic Mapping
# ---------------------------------------------------------------------------

def vector_embedding(data: Dict, job_id: str) -> str:
    meta = data.get("meta", {}) or {}
    cfg = meta.get("config", {}) or {}
    di = meta.get("data_integrity", {}) or {}
    cs = meta.get("context_stats", {}) or {}
    prox = data.get("proximity", {}) or {}
    rows = prox.get("rows", []) or []
    gaps = prox.get("gaps", []) or []
    thresholds = prox.get("thresholds", {}) or {}

    # Proximity detail table
    prox_table = [["Topic", "Entity", "Cosine Distance", "Proximity %", "Label", "High-Rel Docs", "Mentions", "Confidence", "Threshold"]]
    for r in rows:
        prox_val = r.get("proximity")
        prox_pct = f"{float(prox_val) * 100:.1f}%" if prox_val is not None else "&mdash;"
        prox_table.append([
            _esc(r.get("topic", "")),
            _esc(r.get("entity", "")),
            _round(prox_val),
            prox_pct,
            f"<b>{_esc(r.get('label', ''))}</b>",
            _num(r.get("docs_highly_relevant", 0)),
            _num(r.get("support_mentions", 0)),
            _esc(r.get("confidence", "")),
            _round(r.get("threshold_used")),
        ])

    # Gap table
    gap_table = [["Topic", "Brand Proximity", "Best Competitor", "Competitor Proximity", "Gap", "Severity"]]
    for g in gaps:
        gap_table.append([
            _esc(g.get("topic", "")),
            _round(g.get("brand_proximity")),
            _esc(g.get("best_competitor", "")),
            _round(g.get("best_competitor_proximity")),
            _round(g.get("gap")),
            f"<b>{_esc(g.get('severity', ''))}</b>",
        ])

    # Topic thresholds
    topic_thresholds = meta.get("topic_thresholds", {}) or {}
    thresh_table = [["Topic", "Auto-Calibrated Threshold", "Description"]]
    for topic, thresh in topic_thresholds.items():
        thresh_table.append([
            _esc(topic),
            _round(thresh),
            f"Documents with topic similarity &gt; {_round(thresh)} are considered 'highly relevant' to '{_esc(topic)}'",
        ])

    embedding_detail = f"""
    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Embedding Model Configuration</h3>
      {_t([
        ["Parameter", "Value", "Description"],
        ["Embedding model", _esc(di.get("embedding_model", "")),
         "Hugging Face sentence-transformers model loaded locally on CPU/GPU"],
        ["Embedding kind", _esc(di.get("embedding_kind", "")),
         "Engine type: 'sentence-transformers' (real local model) or 'tfidf' (fallback)"],
        ["Models real", "Yes" if di.get("models_real") else "No (fallback)",
         "Whether the tool used real pretrained models or fell back to synthetic/TF-IDF"],
        ["NER model", _esc(di.get("ner_model", di.get("ner_kind", ""))),
         "spaCy NER pipeline for entity extraction"],
        ["Sentiment model", _esc(di.get("sentiment_model", "")),
         "RoBERTa transformer for sentiment classification"],
        ["Auto threshold", "Yes" if cfg.get("auto_threshold") else "No",
         "Automatic calibration of relevance thresholds per topic"],
        ["High-relevance threshold", _round(cfg.get("high_relevance_threshold")),
         "Manual threshold if auto-calibration is disabled"],
        ["Near-dup threshold", _round(cfg.get("near_dup_threshold", 0.95)),
         "Cosine similarity threshold for near-duplicate detection"],
      ])}
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">How Cosine Similarity Works</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant)">
        <p>Every document paragraph, the target brand name, and each competitor
        concept are projected into a shared <b>{cfg.get('embedding_model', '').split('/')[-1]}</b>
        vector space (384–1024 dimensions depending on model). The tool then computes
        the <b>cosine similarity</b> between each entity vector and each topic vector:</p>

        <div style="background:var(--m3-surface-container-high);padding:16px 20px;border-radius:12px;
             font-family:ui-monospace,monospace;font-size:13px;margin:12px 0">
          cosine_similarity(A, B) = (A · B) / (||A|| × ||B||)<br>
          <br>
          where A = entity embedding vector (brand or competitor)<br>
          &nbsp;&nbsp;&nbsp;&nbsp;B = topic embedding vector (industry concept)<br>
          <br>
          Result range: 0.00 (completely unrelated) → 1.00 (identical meaning)
        </div>

        <p>The <b>proximity score</b> reported is actually the <b>cosine distance</b>
        (1 - cosine_similarity), so a lower number means the entity is CLOSER to
        the topic in vector space. This is the mathematical foundation behind every
        RAG retrieval decision.</p>

        <p><b>Document-topic similarity</b> is computed by embedding each RAG-style
        chunk window (512 tokens) separately, then taking the maximum chunk-topic
        similarity as the document's relevance score. This avoids the false-positive
        problem of embedding an entire 3,000-word article as a single vector.</p>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Context Statistics</h3>
      {_t([
        ["Metric", "Value", "Explanation"],
        ["Documents in corpus", _num(cs.get("doc_count", 0)),
         "Clean documents entering vector analysis"],
        ["Graph nodes (entities)", _num(cs.get("graph", {}).get("nodes", 0)),
         "Distinct entities tracked in co-occurrence graph"],
        ["Graph edges (co-occurrences)", _num(cs.get("graph", {}).get("edges", 0)),
         "Entity pairs appearing in the same paragraph"],
        ["Graph density", _round(cs.get("graph", {}).get("density", 0)),
         "Ratio of actual edges to possible edges (0 = no co-occurrence)"],
        ["Proximity comparisons", _num(len(rows)),
         "Total entity × topic cosine distance calculations"],
        ["Gap analyses", _num(len(gaps)),
         "Topic-level brand vs competitor proximity gaps"],
      ])}
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Auto-Calibrated Topic Thresholds</h3>
      <p style="font-size:13px;color:var(--m3-on-surface-variant);margin:0 0 10px">
        When auto-calibration is enabled, the tool analyzes the distribution of
        document-topic similarities for each topic and sets a threshold at the
        elbow point — documents scoring above this are "highly relevant".</p>
      {_t(thresh_table)}
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Full Proximity Score Matrix ({_num(len(rows))} comparisons)</h3>
      {_t(prox_table, row_classes=_classes_for_prox(rows, _brand_l(cfg)))}
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Proximity Gaps ({_num(len(gaps))} topic gaps)</h3>
      {_t(gap_table, row_classes=_classes_for_gap(gaps))}
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Proximity Threshold Legend</h3>
      {_t([
        ["Label", "Distance Range", "Meaning"],
        ["Tight", f"&lt; {_round(thresholds.get('tight', 0.75))}",
         "Entity is strongly associated with this topic in vector space — likely appears in RAG retrievals for this concept"],
        ["Medium", f"{_round(thresholds.get('tight', 0.75))} – {_round(thresholds.get('far', 0.5))}",
         "Moderate association — may appear in extended retrieval results"],
        ["Far", f"&gt; {_round(thresholds.get('far', 0.5))}",
         "Weak or no association — unlikely to appear in RAG retrievals for this topic"],
      ])}
    </div>
    """

    return _wrap(job_id, "vector_embedding",
                 "Engine 2: Local Vector Embedding & Semantic Mapping — Full Analysis",
                 _engine_banner(data, "vector_embedding") + embedding_detail)


# ---------------------------------------------------------------------------
# 3) NER & Knowledge Graphs
# ---------------------------------------------------------------------------

def ner_graphs(data: Dict, job_id: str) -> str:
    meta = data.get("meta", {}) or {}
    cfg = meta.get("config", {}) or {}
    di = meta.get("data_integrity", {}) or {}
    cs = meta.get("context_stats", {}) or {}
    graph = cs.get("graph", {}) or {}
    cite = data.get("citation_gap", {}) or {}
    ent_sum = cite.get("entity_summary", []) or []

    # Entity detail table
    ent_table = [["Entity", "Total Docs", "Mentioned", "Linked", "Unlinked", "Omitted", "Mention Rate", "Link Rate"]]
    for e in ent_sum:
        ent_table.append([
            f"<b>{_esc(e.get('entity', ''))}</b>",
            _num(e.get("docs_total", 0)),
            _num(e.get("docs_mentioned", 0)),
            _num(e.get("docs_linked", 0)),
            _num(e.get("docs_unlinked", 0)),
            _num(e.get("docs_omitted", 0)),
            _pct(e.get("mention_rate_pct", 0)),
            _pct(e.get("link_rate_of_mentions_pct", 0)),
        ])

    # Citation details per document
    citations = cite.get("citations", []) or []
    cit_table = [["Doc ID", "URL", "Title", "Type", "Linked Entities", "Unlinked Entities", "Omitted Entities", "Max Topic", "Max Sim"]]
    for c in citations:
        cit_table.append([
            _esc(c.get("doc_id", "")[:12]),
            f"<a href='{_esc(c.get('url', ''))}' target='_blank'>{_esc((c.get('url', ''))[:50])}...</a>",
            _esc((c.get("title", ""))[:40]),
            _esc(c.get("source_type", "")),
            _num(len(c.get("linked", []) or [])),
            _num(len(c.get("unlinked", []) or [])),
            _num(len(c.get("omitted", []) or [])),
            _esc(c.get("max_topic", "")),
            _round(c.get("max_topic_sim")),
        ])

    ner_detail = f"""
    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">NER Model Configuration</h3>
      {_t([
        ["Parameter", "Value", "Description"],
        ["NER engine", _esc(di.get("ner_kind", "")),
         "spaCy NER pipeline (local, zero-cost)"],
        ["NER model", _esc(di.get("ner_model", "")),
         "Specific spaCy model loaded (en_core_web_sm / md / lg / trf)"],
        ["Entity types extracted", "ORG, PRODUCT, PERSON",
         "Named entity types scanned in every document"],
        ["Total entities tracked", _num(di.get("entities_total", 0)),
         "Distinct brand + competitor entities in the analysis"],
        ["Entities with mentions", _num(di.get("entities_with_mentions", 0)),
         "Entities that actually appear in the corpus"],
        ["Models real", "Yes" if di.get("models_real") else "No",
         "Real spaCy model or synthetic fallback"],
      ])}
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">How NER &amp; Knowledge Graphs Work</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant)">
        <p><b>Step 1: Entity Extraction.</b> Every cleaned document is passed through
        the spaCy NER pipeline which identifies named entities and classifies them
        as Organizations (ORG), Products (PRODUCT), or People (PERSON). Each entity
        mention is recorded with its document position and surrounding context.</p>

        <p><b>Step 2: Entity Normalization.</b> Extracted entities are normalized
        using the configured ontology aliases — e.g., "Acme Corp", "Acme Inc",
        "ACME" all resolve to the canonical entity "Acme". This ensures accurate
        counting across variant name forms.</p>

        <p><b>Step 3: Co-occurrence Matrix.</b> The <code>networkx</code> library
        builds a graph where nodes are entities and edges represent co-occurrence
        in the same paragraph. Edge weight = frequency of co-occurrence. This
        graph reveals which entities are structurally linked in the web's knowledge
        graph — the signal behind citation authority.</p>

        <p><b>Step 4: Graph Analysis.</b> Graph density, clustering coefficient,
        and centrality metrics reveal the structural position of each entity.
        High density between competitor entities and a topic (but low for your
        brand) indicates a citation gap that RAG engines will exploit.</p>

        <p><b>Current graph:</b> {graph.get('nodes', 0)} nodes,
        {graph.get('edges', 0)} edges, density {_round(graph.get('density', 0))}.
        {'No co-occurrence edges detected — entities do not appear in the same paragraphs.' if graph.get('edges', 0) == 0 else ''}</p>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Co-occurrence Graph Statistics</h3>
      {_t([
        ["Metric", "Value", "Interpretation"],
        ["Graph nodes", _num(graph.get("nodes", 0)),
         "Distinct entities (brand + competitors) tracked"],
        ["Graph edges", _num(graph.get("edges", 0)),
         "Entity pairs co-occurring in the same paragraph"],
        ["Graph density", _round(graph.get("density", 0)),
         "0.0 = no connections; 1.0 = fully connected"],
        ["Topic threshold (alpha beta)", _round(meta.get("topic_thresholds", {}).get("alpha beta", 0)),
         "Similarity threshold for 'highly relevant' docs"],
      ])}
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Entity Citation Summary ({_num(len(ent_sum))} entities)</h3>
      {_t(ent_table, row_classes=_classes_for_ledger(ent_sum, _brand_l(cfg)))}
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Per-Document Citation Audit ({_num(len(citations))} documents)</h3>
      <p style="font-size:12px;color:var(--m3-on-surface-variant);margin:0 0 8px">
        Each row shows how a single document treats the brand vs competitors:
        <b>linked</b> (with hyperlink), <b>unlinked</b> (mentioned without link),
        or <b>omitted</b> (not mentioned at all).</p>
      {_t(cit_table)}
    </div>
    """

    return _wrap(job_id, "ner_graphs",
                 "Engine 3: Local NER & Knowledge Graphs — Full Analysis",
                 _engine_banner(data, "ner_graphs") + ner_detail)


# ---------------------------------------------------------------------------
# 4) Citation Gap & Invisibility Index
# ---------------------------------------------------------------------------

def citation_gap(data: Dict, job_id: str) -> str:
    cite = data.get("citation_gap", {}) or {}
    inv = data.get("invisibility", {}) or {}
    di = data.get("meta", {}).get("data_integrity", {}) or {}
    ent_sum = cite.get("entity_summary", []) or []
    off_page = cite.get("off_page_targets", []) or []
    per_topic = inv.get("per_topic", []) or []
    recs = data.get("recommendations", []) or []

    # Invisibility per topic
    inv_table = [["Topic", "Relevant Docs", "Brand Present", "Competitor Present", "Invisibility %", "Vector SoV %", "Threshold"]]
    for t in per_topic:
        inv_table.append([
            _esc(t.get("topic", "")),
            _num(t.get("relevant_docs", 0)),
            _num(t.get("brand_present_docs", 0)),
            _num(t.get("competitor_present_docs", 0)),
            _pct(t.get("topic_invisibility_pct", 0)),
            _pct(t.get("vector_share_of_voice_pct", 0)),
            _round(t.get("threshold_used")),
        ])

    # Off-page targets
    opt_table = [["URL", "Title", "Type", "Topic", "Relevance", "Competitors", "High-Rel"]]
    for t in off_page:
        opt_table.append([
            f"<a href='{_esc(t.get('url', ''))}' target='_blank'>{_esc((t.get('url', ''))[:60])}</a>",
            _esc((t.get("title", ""))[:50]),
            _esc(t.get("source_type", "")),
            _esc(t.get("top_topic", "")),
            _round(t.get("topic_relevance")),
            _num(t.get("competitors_present", 0)),
            "Yes" if t.get("high_relevance") else "No",
        ])

    # Recommendations
    rec_table = [["Rank", "Priority", "Category", "Title", "Score", "Action"]]
    for r in recs:
        rec_table.append([
            _num(r.get("rank", 0)),
            f"<span class='m3-badge'>{_esc(r.get('priority', ''))}</span>",
            _esc(r.get("category", "")),
            _esc((r.get("title", ""))[:60]),
            _round(r.get("score")),
            _esc((r.get("action", ""))[:80]) + "...",
        ])

    citation_detail = f"""
    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">RAG Invisibility Index — Composite Score</h3>
      <div class="m3-grid" style="grid-template-columns:repeat(4,1fr)">
        <div class="m3-kpi"><div class="v" style="color:var(--m3-error)">{_round(cite.get('rag_invisibility_index'))}</div>
          <div class="l">RAG Invisibility Index</div></div>
        <div class="m3-kpi"><div class="v" style="color:var(--m3-tertiary)">{_round(inv.get('composite_invisibility_index_pct'))}%</div>
          <div class="l">Composite Invisibility %</div></div>
        <div class="m3-kpi"><div class="v" style="color:var(--m3-tertiary)">{_round(inv.get('composite_vector_share_of_voice_pct'))}%</div>
          <div class="l">Vector Share of Voice</div></div>
        <div class="m3-kpi"><div class="v">{_num(cite.get('high_relevance_doc_count', 0))}</div>
          <div class="l">High-Relevance Documents</div></div>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">How the Citation Gap &amp; Invisibility Index Work</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant)">
        <p><b>Step 1: Document Relevance Filtering.</b> Documents with topic
        similarity above the auto-calibrated threshold are classified as
        "highly relevant" to that topic. In this run, {_num(cite.get('high_relevance_doc_count', 0))}
        documents met the threshold.</p>

        <p><b>Step 2: Entity Presence Audit.</b> For each highly-relevant document,
        the tool scans for mentions of the target brand and each competitor.
        Mentions are classified as:</p>
        <ul>
          <li><b>Linked mention:</b> Entity appears with a hyperlink (direct citation)</li>
          <li><b>Unlinked mention:</b> Entity appears in text without a hyperlink</li>
          <li><b>Omitted:</b> Entity does not appear in the document at all</li>
        </ul>

        <p><b>Step 3: Invisibility Calculation.</b> Per-topic invisibility =
        (documents where brand is omitted AND at least one competitor appears) /
        (total highly-relevant documents). This is the percentage of relevant
        content where your brand is invisible to RAG engines.</p>

        <p><b>Step 4: Vector Share of Voice.</b> Per-topic SoV = average cosine
        proximity of brand to topic / (brand proximity + best competitor proximity).
        This measures the brand's share of the semantic "space" for each topic.</p>

        <p><b>Step 5: RAG Invisibility Index.</b> The composite score across all
        topics, weighted by topic relevance and document count. Lower = better
        visibility. The index accounts for both structural omission (citation gap)
        and semantic distance (vector proximity).</p>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Per-Topic Invisibility Breakdown</h3>
      {_t(inv_table, row_classes=_classes_for_inv(per_topic))}
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">High-Relevance Off-Page Targets ({_num(len(off_page))} documents)</h3>
      <p style="font-size:12px;color:var(--m3-on-surface-variant);margin:0 0 8px">
        These are the documents most likely to be retrieved by RAG engines for
        your target topics. Each shows competitor presence and topic relevance.</p>
      {_t(opt_table)}
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Actionable Recommendations ({_num(len(recs))} total)</h3>
      <p style="font-size:12px;color:var(--m3-on-surface-variant);margin:0 0 8px">
        Prioritized directives based on the citation gap analysis. P1 = critical
        (immediate action needed), P2 = high priority, P3 = medium priority.</p>
      {_t(rec_table, row_classes=_classes_for_recs(recs))}
    </div>
    """

    return _wrap(job_id, "citation_gap",
                 "Engine 4: Citation Gap & Invisibility Index — Full Analysis",
                 _engine_banner(data, "citation_gap") + citation_detail)


# ---------------------------------------------------------------------------
# 5) RAG Chunking & Contextual Window Simulator
# ---------------------------------------------------------------------------

def chunking_engine(data: Dict, job_id: str) -> str:
    adv = data.get("advanced", {}) or {}
    ch = adv.get("chunking", {}) or {}
    cfg = data.get("meta", {}).get("config", {}) or {}
    per_doc = ch.get("per_doc_windows", {}) or {}

    doc_table = [["Document ID", "Windows Generated", "Retrieved", "Est. Tokens"]]
    total_tokens = 0
    for doc_id, windows in per_doc.items():
        est_tokens = windows * ch.get("chunk_tokens", 512)
        total_tokens += est_tokens
        doc_table.append([
            _esc(doc_id[:16]),
            _num(windows),
            "—" ,
            _num(est_tokens),
        ])

    chunk_detail = f"""
    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Chunking Configuration</h3>
      {_t([
        ["Parameter", "Value", "Description"],
        ["Chunk token size", _num(ch.get("chunk_tokens", 512)),
         "Maximum tokens per RAG retrieval window"],
        ["Overlap tokens", _num(ch.get("chunk_overlap_tokens", 64)),
         "Token overlap between consecutive windows for context preservation"],
        ["Total windows generated", _num(ch.get("window_count", 0)),
         "RAG-style retrieval windows created from the corpus"],
        ["Windows retrieved (top-k)", _num(ch.get("retrieved_count", 0)),
         "Windows that scored in the top-k for their topic"],
        ["Total tokens processed", _num(ch.get("tokens_processed", 0)),
         "BPE tokens across all windows"],
        ["Top-k retrieval", _num(cfg.get("top_k_retrieval", 5)),
         "Number of chunks returned per retrieval query"],
        ["Target entity density", _pct(cfg.get("target_entity_density", 0.015)),
         "Ideal brand mention density within each window"],
      ])}
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Why Chunking Matters for RAG Accuracy</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant)">
        <p><b>The Problem:</b> AI search engines (Google AI Overviews, Perplexity,
        ChatGPT, etc.) do NOT embed entire web pages as single vectors. They split
        pages into <b>retrieval windows</b> of 256–512 tokens each, then embed
        and rank each window independently. A 3,000-word article becomes 4–8 separate
        chunks.</p>

        <p><b>Why naive whole-page scoring fails:</b> If you score an entire article
        as one vector, a page that mentions your brand once in paragraph 3 and
        discusses competitors for the other 90% will show a high "brand proximity"
        score — a massive false positive. The retriever would never actually surface
        your brand from that page because the relevant chunk (where your brand
        appears) is a tiny fraction of the content.</p>

        <p><b>What this engine does:</b> The RAG Chunking Simulator splits every
        harvested document into <b>{ch.get("chunk_tokens", 512)}-token windows</b>
        with <b>{ch.get("chunk_overlap_tokens", 64)}-token overlap</b> (using a
        real BPE tokenizer from HuggingFace tokenizers). Each window is embedded
        independently, and only windows that score above the topic threshold are
        marked as "retrieved". This exactly replicates how a real RAG engine
        processes and ranks content.</p>

        <p><b>Result:</b> {ch.get("window_count", 0)} windows generated from
        {len(per_doc)} documents, {ch.get("retrieved_count", 0)} windows retrieved
        in the top-k. {ch.get("tokens_processed", 0):,} BPE tokens processed
        total.</p>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">BPE Tokenization Details</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant)">
        <p>The tool uses the <b>same BPE tokenizer</b> as the embedding model
        (HuggingFace <code>PreTrainedTokenizerFast</code>), ensuring token counts
        match exactly what the embedding model sees. This is critical because
        token boundaries determine where chunks split, which directly affects
        which content ends up in which retrieval window.</p>

        <p><b>Chunking algorithm:</b></p>
        <ol>
          <li>Tokenize entire document text using BPE</li>
          <li>Split into windows of {ch.get("chunk_tokens", 512)} tokens</li>
          <li>Each window overlaps the previous by {ch.get("chunk_overlap_tokens", 64)} tokens
          (preserving cross-boundary context)</li>
          <li>Embed each window independently using the sentence-transformer</li>
          <li>Score each window against each topic vector</li>
          <li>Mark windows scoring above the topic threshold as "retrieved"</li>
          <li>Apply top-k filtering: only the {cfg.get("top_k_retrieval", 5)} highest-scoring
          windows per topic are considered "in the retrieval result"</li>
        </ol>
      </div>
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Per-Document Window Breakdown ({_num(len(per_doc))} documents)</h3>
      {_t(doc_table)}
    </div>
    """

    return _wrap(job_id, "chunking",
                 "Engine 5: RAG Chunking & Contextual Window Simulator — Full Analysis",
                 _engine_banner(data, "chunking") + chunk_detail)


# ---------------------------------------------------------------------------
# 6) Semantic Drift Tracking
# ---------------------------------------------------------------------------

def drift_tracking(data: Dict, job_id: str) -> str:
    adv = data.get("advanced", {}) or {}
    dr = adv.get("drift", {}) or {}
    per_topic = dr.get("per_topic", []) or []
    alerts = dr.get("alerts", []) or []

    drift_table = [["Topic", "Proximity", "Invisibility %", "SoV %",
                     "Proximity Delta", "Invisibility Delta", "SoV Delta",
                     "Has Prior", "Data Points", "Anomaly"]]
    for t in per_topic:
        drift_table.append([
            _esc(t.get("topic", "")),
            _round(t.get("proximity")),
            _pct(t.get("invisibility_pct")),
            _pct(t.get("sov_pct")),
            _round(t.get("proximity_delta")),
            _pct(t.get("invisibility_delta")),
            _pct(t.get("sov_delta")),
            "Yes" if t.get("has_prior") else "No (first run)",
            _num(t.get("data_points", 0)),
            "⚠ YES" if t.get("anomaly") else "No",
        ])

    alert_table = [["Topic", "Metric", "Alert"]]
    for a in alerts:
        alert_table.append([
            _esc(a.get("topic", "")),
            _esc(a.get("metric", "")),
            _esc(a.get("message", a.get("alert", ""))),
        ])

    drift_detail = f"""
    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Drift Tracking Configuration</h3>
      {_t([
        ["Parameter", "Value", "Description"],
        ["Topics tracked", _num(len(per_topic)),
         "Topics with time-series data points"],
        ["Drift alerts", _num(len(alerts)),
         "Anomalous changes detected since last run"],
        ["History retention", _num(data.get("meta", {}).get("config", {}).get("drift_history_keep", 60)),
         "Maximum number of historical data points retained"],
        ["DuckDB time-series store", "drift_timeseries.duckdb",
         "Persistent database for cross-run metric storage"],
        ["Has prior data", "Yes" if any(t.get("has_prior") for t in per_topic) else "No (first run)",
         "Whether a previous run exists for comparison"],
      ])}
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">How Semantic Drift Tracking Works</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant)">
        <p><b>The Problem:</b> AI search engines continuously re-index the web and
        shift their vector representations. A page that ranked your brand at
        proximity 0.3 to "machine learning" last week might shift to 0.5 this
        week after a competitor publishes a whitepaper. Without tracking, you
        never know when or why your visibility changed.</p>

        <p><b>What this engine does:</b></p>
        <ol>
          <li><b>Snapshots metrics</b> per-topic (proximity, invisibility %, SoV %)
          into a DuckDB time-series database at the end of each run.</li>
          <li><b>Computes deltas</b> by comparing the current run's metrics to the
          most recent prior run for the same brand+topics combination.</li>
          <li><b>Applies anomaly detection</b> — flags any metric that moved more
          than 2 standard deviations from the historical mean as an "anomaly".</li>
          <li><b>Generates alerts</b> with specific descriptions like "Proximity to
          Topic X drifted 12% farther away after Competitor B launched their
          whitepaper."</li>
        </ol>

        <p><b>Cross-run comparison:</b> The delta columns show the absolute change
        since the last run. Positive proximity delta = brand moved AWAY from the
        topic (worse). Negative = brand moved CLOSER (better). The same logic
        applies to invisibility and SoV deltas.</p>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Per-Topic Drift Analysis</h3>
      {_t(drift_table, row_classes=_classes_for_drift(per_topic))}
    </div>
    """

    if alerts:
        drift_detail += f"""
    <div class="card" style="margin:14px 0;border-color:var(--m3-error)">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700;color:var(--m3-error)">
        ⚠ Drift Alerts ({_num(len(alerts))})</h3>
      {_t(alert_table, row_classes=["row-high"] * len(alerts))}
    </div>"""
    else:
        drift_detail += """
    <div class="card" style="margin:14px 0;border-color:var(--m3-tertiary)">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700;color:var(--m3-tertiary)">
        ✓ No Drift Alerts</h3>
      <p style="font-size:13px;color:var(--m3-on-surface-variant)">
        No anomalous metric changes were detected. All metrics are within expected
        historical ranges. Run the audit again later to build time-series data
        for drift detection.</p>
    </div>"""

    return _wrap(job_id, "drift_tracking",
                 "Engine 6: Semantic Drift Tracking & Time-Series DB — Full Analysis",
                 _engine_banner(data, "drift_tracking") + drift_detail)


# ---------------------------------------------------------------------------
# 7) LLM Gap Analysis
# ---------------------------------------------------------------------------

def llm_analysis(data: Dict, job_id: str) -> str:
    adv = data.get("advanced", {}) or {}
    llm = adv.get("llm", {}) or {}
    cfg = data.get("meta", {}).get("config", {}) or {}

    llm_detail = f"""
    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">LLM Gap Analysis Configuration</h3>
      {_t([
        ["Parameter", "Value", "Description"],
        ["Ollama base URL", _esc(cfg.get("ollama_base_url") or "not configured"),
         "Local Ollama server endpoint for LLM inference"],
        ["LLM model", _esc(cfg.get("ollama_model", "llama3")),
         "Local LLM model (llama3, mistral, etc.)"],
        ["Use LLM", "Yes" if cfg.get("use_llm") else "No",
         "Whether LLM-powered gap analysis is enabled"],
        ["LLM available", "Yes" if llm.get("available") else "No",
         "Whether Ollama was reachable at runtime"],
        ["Fallback behavior", "Deterministic metrics still emitted",
         "When LLM is unavailable, all mathematical metrics are computed normally. "
         "Only the free-text rationale is omitted"],
      ])}
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">How Local LLM Gap Analysis Works</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant)">
        <p><b>The Problem:</b> Raw cosine distances and entity counts tell you
        <i>what</i> is happening but not <i>why</i>. Why did the LLM retrieve
        Competitor A's chunk over yours for "best enterprise RAG tools"? The
        mathematical metrics alone can't answer this.</p>

        <p><b>What this engine does:</b> When a local Ollama server is running
        (with Llama 3, Mistral, or any compatible model), the tool feeds the
        retrieved chunks and entity analysis into the LLM with a structured prompt:</p>

        <div style="background:var(--m3-surface-container-high);padding:14px 18px;border-radius:12px;
             font-family:ui-monospace,monospace;font-size:12px;margin:12px 0;line-height:1.6">
          SYSTEM: You are an SEO/RAG analyst. Given the following retrieved chunks<br>
          and entity analysis, explain WHY the AI engine retrieved Competitor A's<br>
          content instead of Brand X for the query "{cfg.get('industry_topics', [''])[0] if cfg.get('industry_topics') else 'topic'}".<br>
          <br>
          USER: [retrieved chunk text + entity mentions + proximity scores]<br>
          <br>
          OUTPUT: A structured gap analysis with:<br>
          &nbsp;1. Why competitor chunk was preferred (semantic signals)<br>
          &nbsp;2. What content is missing from the brand's corpus<br>
          &nbsp;3. Specific writing directives to close the gap<br>
          &nbsp;4. Optimal token placement within the retrieval window
        </div>

        <p><b>Output:</b> The LLM produces a human-readable gap analysis that
        transforms raw vector math into actionable content strategy. This is
        included in the RAG Content Brief deliverable.</p>

        <p><b>Zero-cost guarantee:</b> Ollama runs entirely on the operator's
        machine. No API calls, no data leaves the computer, no paid tokens.</p>
      </div>
    </div>
    """

    # Show LLM output if available
    if llm.get("gap_analysis"):
        llm_detail += f"""
    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">LLM Gap Analysis Output</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant);
           background:var(--m3-surface-container-high);padding:16px 20px;border-radius:12px;
           white-space:pre-wrap">{_esc(llm.get('gap_analysis', ''))}</div>
    </div>"""
    else:
        llm_detail += """
    <div class="card" style="margin-top:14px;border-color:var(--m3-outline-variant)">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">LLM Gap Analysis Output</h3>
      <p style="font-size:13px;color:var(--m3-on-surface-variant)">
        LLM gap analysis was not available for this run. This typically means
        Ollama was not running locally. All mathematical metrics (proximity,
        invisibility, SoV, token density, sentiment, poisoning) were still
        computed normally. To enable LLM analysis:</p>
      <ol style="font-size:13px;color:var(--m3-on-surface-variant);line-height:1.8">
        <li>Install Ollama: <code class="m3-code">curl -fsSL https://ollama.ai/install.sh | sh</code></li>
        <li>Pull a model: <code class="m3-code">ollama pull llama3</code></li>
        <li>Start the server: <code class="m3-code">ollama serve</code></li>
        <li>Configure the base URL in the advanced options panel</li>
      </ol>
    </div>"""

    return _wrap(job_id, "llm_analysis",
                 "Engine 7: Local LLM Summarization & Gap Analysis — Full Analysis",
                 _engine_banner(data, "llm_analysis") + llm_detail)


# ---------------------------------------------------------------------------
# 8) Sentiment Auditor
# ---------------------------------------------------------------------------

def sentiment_audit(data: Dict, job_id: str) -> str:
    adv = data.get("advanced", {}) or {}
    sent = adv.get("sentiment", {}) or {}
    per_entity = sent.get("per_entity", []) or []
    risk_windows = sent.get("risk_windows", []) or []

    ent_table = [["Entity", "Mentions", "Positive %", "Neutral %", "Negative %",
                   "Net Sentiment", "Risk Windows", "Framing"]]
    for e in per_entity:
        ent_table.append([
            f"<b>{_esc(e.get('entity', ''))}</b>",
            _num(e.get("mentions", 0)),
            _pct100(e.get("positive_pct", 0)),
            _pct100(e.get("neutral_pct", 0)),
            _pct100(e.get("negative_pct", 0)),
            _round(e.get("net_sentiment")),
            _num(e.get("risk_windows", 0)),
            _esc(e.get("framing", "")),
        ])

    risk_table = [["Entity", "Window Text", "Sentiment", "Score"]]
    for r in risk_windows:
        risk_table.append([
            _esc(r.get("entity", "")),
            _esc((r.get("snippet", r.get("text", "")))[:300]),
            _esc(r.get("sentiment", ("negative" if float(r.get("polarity", 0) or 0) < 0 else "neutral"))),
            _round(r.get("polarity", r.get("score"))),
        ])

    sent_detail = f"""
    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Sentiment Model Configuration</h3>
      {_t([
        ["Parameter", "Value", "Description"],
        ["Sentiment model", _esc(sent.get("model", "")),
         "RoBERTa transformer trained on tweets for sentiment classification"],
        ["Method", _esc(sent.get("method", "")),
         "How sentiment was computed (transformer vs lexicon fallback)"],
        ["Entities analyzed", _num(len(per_entity)),
         "Brand + competitor entities with sentiment scores"],
        ["Risk windows detected", _num(len(risk_windows)),
         "Retrieval windows with negative-framed entity mentions"],
      ])}
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">How the Sentiment Auditor Works</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant)">
        <p><b>The Problem:</b> RAG engines don't just retrieve based on vector
        proximity — the sentiment of adjacent tokens matters. If an LLM retrieves
        your brand but the surrounding text says "Acme is expensive and unreliable",
        the AI answer will carry that negative framing. This is a "Brand Sentiment
        Risk in RAG" — your brand appears in the answer, but with hostile context.</p>

        <p><b>What this engine does:</b></p>
        <ol>
          <li><b>Sentiment classification:</b> Every retrieved RAG window containing
          an entity mention is classified as positive, neutral, or negative using
          the RoBERTa transformer model.</li>
          <li><b>Entity-level aggregation:</b> Sentiment scores are aggregated per
          entity to produce positive/negative/neutral percentages and a net
          sentiment score (-1.0 to +1.0).</li>
          <li><b>Risk window detection:</b> Windows with negative sentiment toward
          a brand entity are flagged as "risk windows" with the verbatim text
          extracted for manual review.</li>
          <li><b>Framing analysis:</b> The overall framing of each entity is
          classified as "positive", "negative", "mixed", or "neutral" based on
          the distribution of sentiment across windows.</li>
        </ol>

        <p><b>Net sentiment formula:</b> net = positive% - negative%. Range: -1.0
        (all negative) to +1.0 (all positive). A score of 0.0 means perfectly
        balanced or no mentions.</p>
      </div>
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Per-Entity Sentiment Scores ({_num(len(per_entity))} entities)</h3>
      {_t(ent_table, row_classes=_classes_for_sent(per_entity))}
    </div>
    """

    if risk_windows:
        sent_detail += f"""
    <div class="card" style="margin:14px 0;border-color:var(--m3-error)">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700;color:var(--m3-error)">
        ⚠ Risk Windows ({_num(len(risk_windows))} negative-framed mentions)</h3>
      <p style="font-size:12px;color:var(--m3-on-surface-variant);margin:0 0 8px">
        These retrieval windows contain entity mentions with negative sentiment
        context. If an LLM retrieves these chunks, it will propagate the negative
        framing into its generated answer.</p>
      {_t(risk_table, row_classes=["row-critical"] * len(risk_windows))}
    </div>"""
    else:
        sent_detail += """
    <div class="card" style="margin:14px 0;border-color:var(--m3-tertiary)">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700;color:var(--m3-tertiary)">
        ✓ No Risk Windows Detected</h3>
      <p style="font-size:13px;color:var(--m3-on-surface-variant)">
        No retrieval windows with negative sentiment framing toward any tracked
        entity were found. This may indicate the brand has minimal corpus presence
        (zero mentions = zero risk windows) or that all mentions are neutral/positive.</p>
    </div>"""

    return _wrap(job_id, "sentiment",
                 "Engine 8: RAG Chunk Hallucination & Sentiment Auditor — Full Analysis",
                 _engine_banner(data, "sentiment") + sent_detail)


# ---------------------------------------------------------------------------
# 9) Synthetic Query Generator
# ---------------------------------------------------------------------------

def synthetic_queries(data: Dict, job_id: str) -> str:
    adv = data.get("advanced", {}) or {}
    syn = adv.get("synthetic_queries", {}) or {}
    per_entity = syn.get("per_entity", {}) or {}
    cfg = data.get("meta", {}).get("config", {}) or {}

    query_table = [["Entity", "Synthetic Query", "Topic", "Type", "Retrieval Confidence"]]
    for entity, queries in per_entity.items():
        for q in queries:
            query_table.append([
                f"<b>{_esc(entity)}</b>",
                _esc(q.get("query", "")),
                _esc(q.get("topic", "")),
                _esc(q.get("type", "")),
                _round(q.get("retrieval_confidence")),
            ])

    syn_detail = f"""
    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Synthetic Query Generation Configuration</h3>
      {_t([
        ["Parameter", "Value", "Description"],
        ["Synthetic query count", _num(cfg.get("synthetic_query_count", 12)),
         "Maximum queries generated per entity"],
        ["Entities covered", _num(len(per_entity)),
         "Brand + competitor entities with synthetic queries"],
        ["Total queries generated", _num(sum(len(v) for v in per_entity.values())),
         "Total reverse-engineered RAG prompts"],
        ["Query types", "informational, comparison, transactional, navigational",
         "Search intent categories for generated queries"],
      ])}
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">How Synthetic Query Generation Works</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant)">
        <p><b>The Problem:</b> You know what content your competitors have, but you
        don't know what <i>questions</i> users are asking that cause RAG engines
        to retrieve that content. Without knowing the prompt, you can't write
        content that answers it.</p>

        <p><b>What this engine does:</b> It reverse-engineers the retrieval prompts
        by analyzing the semantic characteristics of each entity's top chunks:</p>
        <ol>
          <li><b>Analyze chunk content:</b> For each entity's retrieved windows,
          extract the key concepts, entities, and semantic vectors.</li>
          <li><b>Template matching:</b> Apply the configured search intent templates
          (e.g., "best {{topic}} options", "{{brand}} vs alternatives") with the
          entity and topic substituted.</li>
          <li><b>Confidence scoring:</b> Each synthetic query is scored by how well
          it matches the entity's actual vector proximity to the topic. High
          confidence = the query would likely retrieve this entity's chunks.</li>
          <li><b>Intent classification:</b> Queries are tagged as informational,
          comparison, transactional, etc. to guide content creation strategy.</li>
        </ol>

        <p><b>Actionable output:</b> These synthetic queries become the exact
        Q&A / FAQ targets for your content team. Writing content that answers
        these specific questions — with your brand's entity in the same retrieval
        window — is the most direct path to winning RAG visibility.</p>
      </div>
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">All Generated Synthetic Queries ({_num(sum(len(v) for v in per_entity.values()))} total)</h3>
      {_t(query_table)}
    </div>
    """

    return _wrap(job_id, "synthetic_queries",
                 "Engine 9: Synthetic Query Generator (Reverse-Engineer RAG) — Full Analysis",
                 _engine_banner(data, "synthetic_queries") + syn_detail)


# ---------------------------------------------------------------------------
# 10) Token Density Adjuster
# ---------------------------------------------------------------------------

def token_density(data: Dict, job_id: str) -> str:
    adv = data.get("advanced", {}) or {}
    td = adv.get("token_density", {}) or {}
    per_topic = td.get("per_topic", []) or []
    cfg = data.get("meta", {}).get("config", {}) or {}

    density_table = [["Topic", "Brand Tokens", "Leader", "Leader Tokens",
                       "Brand Density", "Leader Density", "Gap Ratio",
                       "Tokens to Displace", "Target Density",
                       "Brand Proximity", "Leader Proximity", "Severity"]]
    for t in per_topic:
        density_table.append([
            _esc(t.get("topic", "")),
            _num(t.get("brand_on_window_usage_tokens", 0)),
            _esc(t.get("leading_competitor") or "none"),
            _num(t.get("leader_on_window_usage_tokens", 0)),
            _pct(t.get("brand_density", 0)),
            _pct(t.get("leader_density", 0)),
            _round(t.get("density_gap_ratio")),
            _num(t.get("tokens_needed_to_displace", 0)),
            _pct(t.get("target_entity_density", 0.015)),
            _round(t.get("brand_proximity")),
            _round(t.get("leader_proximity")),
            _esc(t.get("severity", "")),
        ])

    action_table = [["Topic", "Recommended Action"]]
    for t in per_topic:
        action_table.append([
            _esc(t.get("topic", "")),
            _esc(t.get("action", "")),
        ])

    density_detail = f"""
    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Token Density Configuration</h3>
      {_t([
        ["Parameter", "Value", "Description"],
        ["Chunk token size", _num(cfg.get("chunk_tokens", 512)),
         "Tokens per RAG retrieval window"],
        ["Target entity density", _pct(cfg.get("target_entity_density", 0.015)),
         "Ideal brand mention density within each window (1.5% default)"],
        ["Top-k retrieval", _num(cfg.get("top_k_retrieval", 5)),
         "Number of chunks returned per retrieval query"],
        ["Brand displacement readiness", f'{_num(td.get("brand_displacement_readiness", 0))}/100',
         "How close the brand is to displacing competitors in top-k"],
        ["Method", _esc(td.get("method", "")),
         "How density was computed (real BPE within-window ratios)"],
      ])}
    </div>

    <div class="card" style="margin-top:14px">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">How the Token Density Adjuster Works</h3>
      <div style="font-size:13px;line-height:1.8;color:var(--m3-on-surface-variant)">
        <p><b>The Problem:</b> Even if your brand has some vector proximity to a
        topic, if the leading competitor occupies more "token space" within the
        retrieved chunks, the RAG engine will prefer their content. Proximity alone
        doesn't tell you how much content you need to write to displace them.</p>

        <p><b>What this engine does:</b></p>
        <ol>
          <li><b>Count brand tokens:</b> Within each top-k retrieved window, count
          how many BPE tokens reference the brand entity (exact match + ontology
          aliases).</li>
          <li><b>Count competitor tokens:</b> Same count for the leading competitor
          in each window.</li>
          <li><b>Compute density:</b> brand_density = brand_tokens / window_tokens.
          leader_density = leader_tokens / window_tokens.</li>
          <li><b>Calculate displacement:</b> How many additional brand tokens are
          needed within the top-k windows to reach the target density
          ({_pct(cfg.get("target_entity_density", 0.015))}) and overtake the
          competitor's density.</li>
          <li><b>Generate action plan:</b> A specific writing directive: "Publish
          an on-topic section of ~X tokens that co-mentions the brand with the
          leading entity and topic terms, targeting ~Y brand mentions across the
          top-{cfg.get('top_k_retrieval', 5)} retrieval windows."</li>
        </ol>

        <p><b>Why this matters:</b> This transforms abstract "improve your SEO"
        advice into a concrete content specification: exact token count, exact
        entity placement, exact density target. A content writer can follow this
        directive precisely.</p>
      </div>
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Per-Topic Density Analysis ({_num(len(per_topic))} topics)</h3>
      {_t(density_table, row_classes=_classes_for_density(per_topic))}
    </div>

    <div class="card" style="margin:14px 0">
      <h3 style="margin:0 0 10px;font-size:16px;font-weight:700">Content Action Plans</h3>
      <p style="font-size:12px;color:var(--m3-on-surface-variant);margin:0 0 8px">
        For each topic where the brand trails, here is the exact content specification
        needed to displace the leading competitor from top-{cfg.get('top_k_retrieval', 5)} retrieval.</p>
      {_t(action_table)}
    </div>
    """

    return _wrap(job_id, "token_density",
                 "Engine 10: Automated Token Density Adjuster — Full Analysis",
                 _engine_banner(data, "token_density") + density_detail)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def render_deep(job_id: str, feature: str, data: Dict) -> str:
    """Dispatch to the correct deep-dive page generator."""
    fn = _DISPATCH.get(feature)
    if fn is None:
        return "<p class='muted'>Unknown feature.</p>"
    return fn(data, job_id)


# ---------------------------------------------------------------------------
# Consolidated single-page renderer (Step 2 "Analysis")
# ---------------------------------------------------------------------------

# (feature key, nav-number, display title) in presentation order
_ALL_SECTIONS = [
    ("web_harvester", "1", "1 · Zero-Cost Headless Web Harvester"),
    ("vector_embedding", "2", "2 · Local Vector Embedding &amp; Semantic Mapping"),
    ("ner_graphs", "3", "3 · Local NER &amp; Knowledge Graphs"),
    ("citation_gap", "4", "4 · Unlinked Authority &amp; Citation Gap Finder"),
    ("chunking", "5", "5 · RAG Chunking &amp; Contextual-Window Simulator"),
    ("drift_tracking", "6", "6 · Semantic Drift Tracking &amp; Time-Series DB"),
    ("llm_analysis", "7", "7 · Local LLM Summarization &amp; Gap Analysis"),
    ("sentiment", "8", "8 · RAG Chunk Hallucination &amp; Sentiment Auditor"),
    ("synthetic_queries", "9", "9 · Synthetic Query Generator (Reverse-Engineer RAG)"),
    ("token_density", "10", "10 · Automated Token Density Adjuster"),
]

_SECTION_TAGS = {
    "web_harvester": "Web Harvester",
    "vector_embedding": "Vector Embedding",
    "ner_graphs": "NER &amp; Graphs",
    "citation_gap": "Citation Gap",
    "chunking": "RAG Chunking",
    "drift_tracking": "Drift Tracking",
    "llm_analysis": "LLM Analysis",
    "sentiment": "Sentiment Audit",
    "synthetic_queries": "Synthetic Queries",
    "token_density": "Token Density",
}

_DISPATCH = {
    "web_harvester": web_harvester,
    "vector_embedding": vector_embedding,
    "ner_graphs": ner_graphs,
    "citation_gap": citation_gap,
    "chunking": chunking_engine,
    "drift_tracking": drift_tracking,
    "llm_analysis": llm_analysis,
    "sentiment": sentiment_audit,
    "synthetic_queries": synthetic_queries,
    "token_density": token_density,
}


def render_all(job_id: str, data: Dict) -> str:
    """Render the entire Step-2 analysis on one page: the narrative summary
    plus every micro-engine's full computed detail, stacked with a jump-nav."""
    from . import narrative as _narr

    # 1) The narrative summary block (methodology + verification)
    summary = _narr.features_html(data, job_id)

    # 1b) Run-global issue summary: bold color-coded problems first so an
    # executive sees every red flag before scrolling a single engine.
    try:
        from . import issues as _issues

        _all_issues = _issues.collect_issues(data)
        _issues_head = (
            '<h2 class="m3-h2" style="margin-top:6px">Issues requiring attention</h2>'
            + _issues.summary_strip_html(_all_issues)
            + _issues.banner_html(_all_issues, engine=None, limit=8)
        )
    except Exception:  # noqa: BLE001 — highlighting must never break a page
        _issues_head = ""

    # 2) In-page jump nav across all engines
    jump = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 4px">'
    for key, num, _label in _ALL_SECTIONS:
        tag = _SECTION_TAGS[key]
        jump += (
            f'<a href="#deep-{key}" style="background:var(--m3-surface-container-high);'
            f'border:1px solid var(--m3-outline-variant);color:var(--m3-on-surface);'
            f'padding:7px 12px;border-radius:10px;font-size:12px;font-weight:700;'
            f'text-decoration:none">{tag}</a>'
        )
    jump += "</div>"

    # 3) Each engine's full detail — extracted body + a section heading.
    # The generator wraps with _wrap (h2 + nav). We swap the bundled nav for a
    # clean in-page heading and an anchor, so they stack on one page.
    blocks = []
    for key, num, title in _ALL_SECTIONS:
        full = _DISPATCH[key](data, job_id)
        body = _extract_body(full)
        blocks.append(
            f'<section id="deep-{key}" style="margin-top:34px">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
            f'<span style="background:var(--m3-primary);color:var(--m3-on-primary);'
            f'font-weight:800;font-size:13px;width:30px;height:30px;border-radius:50%;'
            f'display:inline-flex;align-items:center;justify-content:center">{num}</span>'
            f'<h2 class="m3-h2" style="margin:0;font-size:20px">{title}</h2></div>'
            f'{body}'
            f'</section>'
        )

    return (
        '<div class="narrative">'
        + _issues_head
        + summary
        + '<h2 class="m3-h2" style="margin-top:34px">Jump to a full engine breakdown</h2>'
        + jump
        + "".join(blocks)
        + "</div>"
    )


def _extract_body(full_html: str) -> str:
    """Given a _wrap()'d page, strip its leading <h2> and tab nav so the content
    can be embedded inside a consolidated page (rather than as standalone page)."""
    # The _wrap output is: <h2 ...>{title}</h2>{nav}{body}
    # Drop up to and including the nav <div class="topnav">...</div>.
    h2_end = full_html.find("</h2>")
    if h2_end == -1:
        return full_html
    after_h2 = full_html[h2_end + len("</h2>"):]
    nav_end = after_h2.find("</div>")
    if nav_end == -1:
        return after_h2
    return after_h2[nav_end + len("</div>"):]
