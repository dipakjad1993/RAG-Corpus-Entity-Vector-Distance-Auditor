"""Server-side enterprise PDF generation (reportlab).

Produces a real, downloadable PDF (not a browser print) from the same computed
``data`` dict the dashboard consumes. All figures come from the audit output so
the document cannot contradict the actual results.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

# ---- palette -------------------------------------------------------------
ACCENT = colors.HexColor("#6d8bff")
ACCENT2 = colors.HexColor("#34d399")
DARK = colors.HexColor("#0b0e14")
INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#5b6b86")
LINE = colors.HexColor("#dde4ef")
ALT = colors.HexColor("#eef2f8")
BAD = colors.HexColor("#fb7185")
WARN = colors.HexColor("#fbbf24")


def _e(s: Any) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _pct(x: Any, nd: int = 1) -> str:
    try:
        return f"{float(x) * 100:.{nd}f}%"
    except (TypeError, ValueError):
        return "—"


def _num(x: Any) -> str:
    try:
        return f"{x:,}"
    except (TypeError, ValueError):
        return _e(x)


def _r(x: Any, nd: int = 3) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def _styles() -> Dict[str, ParagraphStyle]:
    ss = getSampleStyleSheet()
    out = {}
    out["title"] = ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold",
                                  fontSize=20, textColor=colors.white, leading=24)
    out["subtitle"] = ParagraphStyle("st", fontName="Helvetica", fontSize=11,
                                     textColor=colors.white, leading=15)
    out["h2"] = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=14,
                               textColor=ACCENT, spaceBefore=16, spaceAfter=6, leading=17)
    out["h3"] = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11.5,
                               textColor=INK, spaceBefore=8, spaceAfter=3)
    out["body"] = ParagraphStyle("b", fontName="Helvetica", fontSize=9.5,
                                 textColor=INK, leading=13.5, alignment=TA_LEFT, spaceAfter=5)
    out["small"] = ParagraphStyle("sm", fontName="Helvetica", fontSize=8,
                                  textColor=MUTED, leading=11)
    out["kpi"] = ParagraphStyle("kpi", fontName="Helvetica-Bold", fontSize=22,
                                textColor=INK, alignment=1, leading=24)
    out["kpil"] = ParagraphStyle("kpil", fontName="Helvetica", fontSize=7.5,
                                 textColor=MUTED, alignment=1, leading=9)
    out["cell"] = ParagraphStyle("c", fontName="Helvetica", fontSize=8, textColor=INK, leading=10.5)
    out["cellh"] = ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=8,
                                  textColor=colors.white, leading=10.5)
    out["big"] = ParagraphStyle("big", fontName="Helvetica-Bold", fontSize=30,
                                textColor=BAD, alignment=1, leading=32)
    return out


def _section_bar(text: str, styles: Dict[str, ParagraphStyle]) -> Table:
    p = Paragraph(text, styles["h2"])
    bar = Table([[p]], colWidths=[170 * mm])
    bar.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, 0), 3, ACCENT),
        ("LEFTPADDING", (0, 0), (0, 0), 8),
        ("TOPPADDING", (0, 0), (0, 0), 2),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
    ]))
    return bar


def _kv_table(rows: List[List[str]], styles: Dict[str, ParagraphStyle]) -> Table:
    data = [[Paragraph(_e(k), styles["cell"]), Paragraph(_e(v), styles["cell"])] for k, v in rows]
    t = Table(data, colWidths=[60 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (0, -1), ALT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _grid_table(header: List[str], rows: List[List[Any]], styles: Dict[str, ParagraphStyle],
                widths: List[float]) -> Table:
    data = [[Paragraph(_e(h), styles["cellh"]) for h in header]]
    for r in rows:
        data.append([Paragraph(_e(c), styles["cell"]) for c in r])
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ALT]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def render_report_pdf(data: Dict[str, Any], job_id: str, out_path: str) -> str:
    meta = data.get("meta", {}) or {}
    cfg = meta.get("config", {}) or {}
    di = meta.get("data_integrity", {}) or {}
    hs = meta.get("harvest_stats", {}) or {}
    cs = meta.get("context_stats", {}) or {}
    prox = data.get("proximity", {}) or {}
    rows = prox.get("rows", []) or []
    cite = data.get("citation_gap", {}) or {}
    inv = data.get("invisibility", {}) or {}
    recs = data.get("recommendations", []) or []
    prov = data.get("provenance", []) or []

    styles = _styles()
    brand = _e(cfg.get("target_brand", ""))

    # ---- doc with footer -------------------------------------------------
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(20 * mm, 14 * mm, 190 * mm, 14 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 9 * mm,
                          f"RAG Corpus Entity & Vector Distance Auditor  •  {brand}  •  Job {job_id}")
        canvas.drawRightString(190 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(
        out_path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title="RAG Corpus Entity & Vector Distance Auditor — Audit Report",
        author="ragevda",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=footer)])

    el: List[Any] = []

    # ---- cover band ------------------------------------------------------
    verified = bool(di.get("verified"))
    badge = "VERIFIED" if verified else "PARTIAL"
    cover = Table([[
        Paragraph("RAG Corpus Entity &amp; Vector Distance Auditor",
                  styles["title"]),
    ], [
        Paragraph("Enterprise Audit Report", styles["subtitle"]),
    ], [
        Paragraph(
            f"Target brand: <b>{brand}</b> &nbsp;|&nbsp; Generated: "
            f"{_e(meta.get('generated_at', ''))} &nbsp;|&nbsp; "
            f"Verification: <b>{badge} ({_r(di.get('verification_score'))}/100)</b>",
            styles["subtitle"]),
    ]], colWidths=[170 * mm])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("LINEBELOW", (0, 0), (-1, -1), 3, ACCENT2),
    ]))
    el.append(cover)
    el.append(Spacer(1, 10))

    # ---- executive summary ----------------------------------------------
    n_topics = len(cfg.get("industry_topics", []) or [])
    n_comp = len(cfg.get("competitor_entities", []) or [])
    inv_idx = cite.get("rag_invisibility_index")
    el.append(_section_bar("1. Executive Summary", styles))
    summary = (
        f"This audit harvested <b>{_num(hs.get('fetched'))}</b> web documents "
        f"({_num(cs.get('doc_count'))} after cleaning) for <b>{brand}</b> across "
        f"<b>{n_topics}</b> topics and <b>{n_comp}</b> competitors using a "
        f"<b>{_e(meta.get('embedding_kind', ''))}</b> embedding engine and "
        f"<b>{_e(meta.get('ner_kind', ''))}</b> NER. The brand's "
        f"<b>RAG Invisibility Index</b> is <b>{_r(inv_idx)}</b> "
        f"({_pct(inv.get('composite_invisibility_index_pct'))} composite) and its "
        f"vector share of voice is <b>{_pct(inv.get('composite_vector_share_of_voice_pct'))}</b>. "
        f"The report surfaces <b>{_num(len(recs))}</b> prioritized off-page "
        f"recommendations and <b>{_num(len(prov))}</b> sourced documents. "
        f"Data-integrity verification scored <b>{_r(di.get('verification_score'))}/100</b> "
        f"({badge})."
    )
    el.append(Paragraph(summary, styles["body"]))

    # ---- inputs ----------------------------------------------------------
    el.append(_section_bar("2. Audit Inputs", styles))
    inputs = [
        ["Target brand", brand],
        ["Industry topics", ", ".join(_e(t) for t in cfg.get("industry_topics", []) or [])],
        ["Competitor entities", ", ".join(_e(c) for c in cfg.get("competitor_entities", []) or [])],
        ["Crawl depth", _num(cfg.get("crawl_depth"))],
        ["Locality", _e(cfg.get("locality") or "global")],
        ["Harvester", _e(cfg.get("harvester", ""))],
        ["Embedding model", _e(cfg.get("embedding_model", ""))],
        ["NER model", _e(cfg.get("spacy_model", ""))],
        ["Relevance threshold (auto)", "yes" if cfg.get("auto_threshold") else f'{cfg.get("high_relevance_threshold")}'],
    ]
    el.append(_kv_table(inputs, styles))

    # ---- verification ----------------------------------------------------
    el.append(_section_bar("3. Methodology &amp; Verification", styles))
    vrows = [
        ["Embedding engine", _e(meta.get("embedding_kind", ""))],
        ["NER engine", _e(meta.get("ner_kind", ""))],
        ["Real models (no synthetic fallback)", "yes" if di.get("models_real") else "no"],
        ["Harvest succeeded", "yes" if di.get("harvest_ok") else "no"],
        ["Documents harvested", _num(di.get("harvested_docs"))],
        ["Near-duplicates removed", _num(di.get("dedup_removed"))],
        ["Entities with mentions", f'{_num(di.get("entities_with_mentions"))} / {_num(di.get("entities_total"))}'],
        ["Provenance complete", "yes" if di.get("provenance_complete") else "partial"],
        ["Verification score", f'{_r(di.get("verification_score"))} / 100  ({badge})'],
    ]
    el.append(_kv_table(vrows, styles))
    el.append(Spacer(1, 4))
    el.append(Paragraph(
        "All scores derive from live harvested content and local model inference. "
        "Semantic proximity and NER are model-derived estimates; the verification "
        "layer confirms provenance, model authenticity and corpus integrity rather "
        "than asserting external factual truth of third-party pages.", styles["small"]))

    # ---- four engines ----------------------------------------------------
    el.append(_section_bar("4. The Four Local Micro-Engines", styles))

    avg_prox = None
    if rows:
        vals = [r.get("proximity") for r in rows if isinstance(r.get("proximity"), (int, float))]
        if vals:
            avg_prox = statistics.mean(vals)
    ent_sum = cite.get("entity_summary", []) or []
    linked = sum(int(e.get("docs_linked", 0) or 0) for e in ent_sum)
    unlinked = sum(int(e.get("docs_unlinked", 0) or 0) for e in ent_sum)
    omitted = sum(int(e.get("docs_omitted", 0) or 0) for e in ent_sum)

    engines = [
        ("A. Zero-Cost Headless Web Harvester",
         "Drives DuckDuckGo / SearXNG / Playwright to pull top pages, Reddit "
         "threads and news, then cleanrooms the HTML (BeautifulSoup / trafilatura) "
         "to isolate pure body text.",
         [f'{_num(hs.get("queries"))} queries', f'{_num(hs.get("fetched"))} pages fetched',
          f'{_num(hs.get("dedup_removed"))} duplicates removed', f'{_num(cs.get("doc_count"))} clean docs']),
        ("B. Local Vector Embedding &amp; Semantic Mapping",
         f"Projects paragraphs, the brand and competitors into a shared vector "
         f"space with sentence-transformers and computes exact cosine similarity "
         f"(0.00 unrelated &rarr; 1.00 identical).",
         [f'{_e(meta.get("embedding_kind", ""))}', f'{_num(len(rows))} comparisons',
          f'mean proximity {_r(avg_prox)}']),
        ("C. Local NER &amp; Knowledge Graphs",
         f"spaCy extracts ORG / PRODUCT / PERSON entities and networkx builds a "
         f"co-occurrence matrix of brand vs competitor topical proximity.",
         [f'{_e(meta.get("ner_kind", ""))}', f'{_num(di.get("entities_total"))} entities',
          f'{_num(len(ent_sum))} audited']),
        ("D. Unlinked Authority &amp; Citation Gap Finder",
         "Classifies each article as linked, unlinked mention or omitted for the "
         "brand and every competitor, powering the RAG Invisibility Index.",
         [f'invisibility {_r(inv_idx)}', f'{_num(cite.get("high_relevance_doc_count"))} high-rel docs',
          f'{_num(linked)} linked / {_num(unlinked)} unlinked / {_num(omitted)} omitted']),
    ]
    for title, desc, chips in engines:
        el.append(Paragraph(title, styles["h3"]))
        el.append(Paragraph(desc, styles["body"]))
        chip_row = " &nbsp;•&nbsp; ".join(_e(c) for c in chips)
        el.append(Paragraph(f'<font color="#6d8bff"><b>{chip_row}</b></font>', styles["small"]))
        el.append(Spacer(1, 4))

    # ---- results ---------------------------------------------------------
    el.append(_section_bar("5. Results", styles))
    el.append(Paragraph(
        f"RAG Invisibility Index: <b>{_r(inv_idx)}</b> &mdash; the share of "
        f"high-ranking industry articles where {brand} is absent while competitors "
        f"are co-cited. Lower is better.", styles["body"]))
    el.append(Spacer(1, 6))
    el.append(Paragraph("5.1 Semantic Vector Proximity", styles["h3"]))
    prox_rows = [[r.get("topic"), r.get("entity"), _r(r.get("proximity")),
                  r.get("label"), _num(r.get("docs_highly_relevant"))]
                 for r in rows[:30]]
    el.append(_grid_table(
        ["Topic", "Entity", "Proximity", "Label", "High-rel docs"],
        prox_rows, styles, [42, 38, 22, 38, 26]))

    el.append(Paragraph("5.2 Entity Citation Summary", styles["h3"]))
    cite_rows = [[e.get("entity"), _num(e.get("docs_total")), _num(e.get("docs_mentioned")),
                  _num(e.get("docs_linked")), _num(e.get("docs_unlinked")),
                  _num(e.get("docs_omitted")), _pct(e.get("mention_rate_pct"))]
                 for e in ent_sum[:15]]
    el.append(_grid_table(
        ["Entity", "Docs", "Mentioned", "Linked", "Unlinked", "Omitted", "Mention %"],
        cite_rows, styles, [34, 18, 22, 18, 20, 18, 22]))

    el.append(Paragraph("5.3 High-Density Off-Page Targets", styles["h3"]))
    opt_rows = [[ (t.get("title") or t.get("url")), t.get("source_type"),
                  t.get("top_topic"), _r(t.get("topic_relevance")), _num(t.get("competitors_present"))]
                 for t in cite.get("off_page_targets", [])[:15]]
    el.append(_grid_table(
        ["URL / Title", "Type", "Top topic", "Relevance", "Competitors"],
        opt_rows, styles, [70, 22, 36, 22, 22]))

    el.append(Paragraph("5.4 Actionable Recommendations", styles["h3"]))
    rec_rows = [[r.get("priority"), r.get("title"), r.get("category"), _r(r.get("score"))]
                for r in recs[:15]]
    el.append(_grid_table(
        ["Priority", "Directive", "Category", "Score"],
        rec_rows, styles, [18, 92, 34, 18]))

    el.append(Spacer(1, 8))
    el.append(HRFlowable(width="100%", color=LINE))
    el.append(Paragraph(
        "Generated locally by ragevda. Figures are reproducible from the job's "
        "report.json. This document is a decision-support artifact, not a "
        "certification of third-party content accuracy.", styles["small"]))

    doc.build(el)
    return out_path
