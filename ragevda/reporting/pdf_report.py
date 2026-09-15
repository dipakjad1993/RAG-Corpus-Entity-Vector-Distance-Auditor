"""Server-side enterprise PDF generation (reportlab).

Executive-grade, print-ready audit report built from the same computed ``data``
dict the dashboard consumes: cover page, contents, executive summary with KPI
cards and charts, all 11 inputs, verification, the four core micro-engines,
all six RAG subfunctions, poisoning + engine-matrix analysis, and the complete
outputs section with full data tables.

2026 print standards applied throughout: a single 170 mm grid every table and
chart aligns to, one Material-3-derived palette, consistent type scale, captioned
charts with methods notes, and page furniture (rule + brand/job + page number)
on every page. Missing quantities render as em dashes, never invented.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Tuple


def _rl():
    """Lazy reportlab imports — keeps /health + web boot at ~0MB.

    reportlab (~7MB + fonts) is only loaded inside build_pdf()/render path,
    never at module import. Required for Render free 512MB (RAGEVDA_LITE).
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate, Frame, HRFlowable, PageTemplate, Paragraph,
        Spacer, Table, TableStyle,
    )
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.shapes import Drawing, Line, String
    return {
        "colors": colors, "TA_CENTER": TA_CENTER, "TA_LEFT": TA_LEFT,
        "A4": A4, "ParagraphStyle": ParagraphStyle,
        "getSampleStyleSheet": getSampleStyleSheet, "mm": mm,
        "BaseDocTemplate": BaseDocTemplate, "Frame": Frame,
        "HRFlowable": HRFlowable, "PageTemplate": PageTemplate,
        "Paragraph": Paragraph, "Spacer": Spacer, "Table": Table,
        "TableStyle": TableStyle, "VerticalBarChart": VerticalBarChart,
        "Pie": Pie, "Drawing": Drawing, "Line": Line, "String": String,
    }

# ---- enterprise print palette: HEX strings at import (zero-cost boot).
# render_report_pdf() upgrades these globals to real reportlab Color objects
# via _ensure_pdf_deps() on first actual PDF build. Import-time cost: ~0MB.
PRIMARY = "#6750A4"
PRIMARY_DARK = "#4F378B"
ON_PRIMARY = "#FFFFFF"
PRIMARY_CONTAINER = "#EADDFF"
SECONDARY = "#625B71"
TERTIARY = "#7D5260"
TERTIARY_CONTAINER = "#FFD8E4"
COVER_BG = "#17141F"
COVER_RULE = "#D0BCFF"
INK = "#1C1B1F"
MUTED = "#49454F"
LINE = "#CAC4D0"
ALT = "#F4EFFA"
ALT2 = "#EDE7F6"
BAD = "#BA1A1A"
WARN = "#8A6100"
GOOD = "#2F7A3E"
CALL_BG = {
    "critical": "#FDECEA",
    "high": "#FFF4D6",
    "medium": "#F4EFFA",
    "good": "#E7F3EA",
}
CALL_BAR = {
    "critical": "#BA1A1A",
    "high": "#9A6B00",
    "medium": "#6750A4",
    "good": "#2F7A3E",
}
SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "good": 3}
CHART_COLORS = [
    "#6750A4", "#7D5260",
    "#4C7C5C", "#8A6100",
    "#42599E", "#9C4048",
    "#5B5BD6", "#2E7D6F",
]

PRIMARY_HEX = "#6750A4"
GRID_WIDTH = 170.0  # mm — every table/chart aligns to this single grid


_PDF_DEPS = None


def _ensure_pdf_deps():
    """Import reportlab lazily + upgrade palette globals to real Colors.

    Called at the top of render_report_pdf() (and build_pdf alias). Keeps
    `import ragevda.webapp` / `/health` free of the ~7MB reportlab import
    plus pandas/torch chains on Render free tier.
    """
    global _PDF_DEPS
    global PRIMARY, PRIMARY_DARK, ON_PRIMARY, PRIMARY_CONTAINER
    global SECONDARY, TERTIARY, TERTIARY_CONTAINER, COVER_BG, COVER_RULE
    global INK, MUTED, LINE, ALT, ALT2, BAD, WARN, GOOD
    global CALL_BG, CALL_BAR, CHART_COLORS
    if _PDF_DEPS is not None:
        return _PDF_DEPS
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate, Frame, HRFlowable, PageTemplate, Paragraph,
        Spacer, Table, TableStyle,
    )
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.shapes import Drawing, Line, String
    H = colors.HexColor
    PRIMARY = H(PRIMARY)
    PRIMARY_DARK = H(PRIMARY_DARK)
    ON_PRIMARY = H(ON_PRIMARY)
    PRIMARY_CONTAINER = H(PRIMARY_CONTAINER)
    SECONDARY = H(SECONDARY)
    TERTIARY = H(TERTIARY)
    TERTIARY_CONTAINER = H(TERTIARY_CONTAINER)
    COVER_BG = H(COVER_BG)
    COVER_RULE = H(COVER_RULE)
    INK = H(INK)
    MUTED = H(MUTED)
    LINE = H(LINE)
    ALT = H(ALT)
    ALT2 = H(ALT2)
    BAD = H(BAD)
    WARN = H(WARN)
    GOOD = H(GOOD)
    CALL_BG = {k: H(v) for k, v in CALL_BG.items()}
    CALL_BAR = {k: H(v) for k, v in CALL_BAR.items()}
    CHART_COLORS = [H(c) for c in CHART_COLORS]
    _PDF_DEPS = {
        "colors": colors, "TA_CENTER": TA_CENTER, "TA_LEFT": TA_LEFT,
        "A4": A4, "ParagraphStyle": ParagraphStyle,
        "getSampleStyleSheet": getSampleStyleSheet, "mm": mm,
        "BaseDocTemplate": BaseDocTemplate, "Frame": Frame,
        "HRFlowable": HRFlowable, "PageTemplate": PageTemplate,
        "Paragraph": Paragraph, "Spacer": Spacer, "Table": Table,
        "TableStyle": TableStyle, "VerticalBarChart": VerticalBarChart,
        "Pie": Pie, "Drawing": Drawing, "Line": Line, "String": String,
    }
    return _PDF_DEPS


def build_pdf(*args, **kwargs):
    """Alias kept for API compat — lazy-loads reportlab then delegates."""
    return render_report_pdf(*args, **kwargs)


# PEP 562 lazy fallback: any legacy bare reference (Paragraph, Table, mm,
# colors, …) resolves via _ensure_pdf_deps() on first use and is cached in
# globals, so all 1200 lines below keep working unchanged with zero
# import-time cost.
def __getattr__(name: str):
    _LAZY_NAMES = {
        "colors", "TA_CENTER", "TA_LEFT", "A4", "ParagraphStyle",
        "getSampleStyleSheet", "mm", "BaseDocTemplate", "Frame",
        "HRFlowable", "PageTemplate", "Paragraph", "Spacer", "Table",
        "TableStyle", "VerticalBarChart", "Pie", "Drawing", "Line", "String",
    }
    if name in _LAZY_NAMES:
        deps = _ensure_pdf_deps()
        globals()[name] = deps[name]
        return deps[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _e(s: Any) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _t(s: Any, n: int = 120) -> str:
    """Escape + truncate long cell text so tables stay on the grid."""
    text = "" if s is None else str(s)
    text = text.replace("\n", " ").strip()
    if len(text) > n:
        text = text[: max(0, n - 1)] + "…"
    return _e(text)


def _pct(x: Any, nd: int = 1) -> str:
    """Fraction 0..1 -> percent. Already-percent 0..100 values pass through."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if v > 1.5:  # already a percent (e.g. 18.1 = 18.1%), do not *100 again
        return f"{v:.{nd}f}%"
    return f"{v * 100:.{nd}f}%"


def _pct100(x: Any, nd: int = 1) -> str:
    """Value already in 0..100 percent units -> percent string (no scaling)."""
    try:
        return f"{float(x):.{nd}f}%"
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
    out: Dict[str, ParagraphStyle] = {}
    out["cover_title"] = ParagraphStyle("ct", parent=ss["Title"], fontName="Helvetica-Bold",
                                        fontSize=24, textColor=colors.white, leading=28)
    out["cover_sub"] = ParagraphStyle("cs", fontName="Helvetica", fontSize=12,
                                      textColor=COVER_RULE, leading=15)
    out["cover_meta"] = ParagraphStyle("cm", fontName="Helvetica", fontSize=9.5,
                                       textColor=colors.white, leading=13.5)
    out["cover_badge"] = ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=10,
                                        textColor=colors.white, leading=13, alignment=TA_CENTER)
    out["h2num"] = ParagraphStyle("h2n", fontName="Helvetica-Bold", fontSize=13,
                                  textColor=colors.white, leading=16, alignment=TA_CENTER)
    out["h2"] = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13,
                               textColor=colors.white, leading=16)
    out["h3"] = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11,
                               textColor=INK, spaceBefore=10, spaceAfter=4, leading=14)
    out["body"] = ParagraphStyle("b", fontName="Helvetica", fontSize=9.5,
                                 textColor=INK, leading=14, alignment=TA_LEFT, spaceAfter=6)
    out["bullet"] = ParagraphStyle("bl", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5,
                                   textColor=INK, leading=13.5, leftIndent=12, spaceAfter=3)
    out["small"] = ParagraphStyle("sm", fontName="Helvetica", fontSize=8,
                                  textColor=MUTED, leading=11)
    out["caption"] = ParagraphStyle("cp", fontName="Helvetica-Oblique", fontSize=7.5,
                                    textColor=MUTED, leading=10, alignment=TA_CENTER, spaceBefore=2)
    out["kpi"] = ParagraphStyle("kpi", fontName="Helvetica-Bold", fontSize=20,
                                textColor=INK, alignment=TA_CENTER, leading=22)
    out["kpil"] = ParagraphStyle("kpil", fontName="Helvetica", fontSize=7.5,
                                 textColor=MUTED, alignment=TA_CENTER, leading=9)
    out["cell"] = ParagraphStyle("c", fontName="Helvetica", fontSize=8, textColor=INK, leading=10.5)
    out["cellh"] = ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=8,
                                  textColor=colors.white, leading=10.5)
    out["toc"] = ParagraphStyle("toc", fontName="Helvetica", fontSize=9.5,
                                textColor=INK, leading=14)
    return out


def _section_band(num: str, title: str, styles: Dict[str, ParagraphStyle]) -> Table:
    """Full-grid section header: numbered pill + white title on primary band."""
    left = Paragraph(f"<b>{_e(num)}</b>", styles["h2num"])
    right = Paragraph(title, styles["h2"])
    bar = Table([[left, right]], colWidths=[16 * mm, (GRID_WIDTH - 16) * mm])
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (0, 0), 4),
        ("RIGHTPADDING", (1, 0), (1, 0), 8),
        ("ROUNDEDCORNERS", [3, 3, 3, 3]),
    ]))
    return bar


def _hot(text: str, hex_color: str) -> str:
    """Bold color-coded cell value (red/amber/green). Input must be pre-escaped."""
    return f'<font color="{hex_color}"><b>{text}</b></font>'


def _sev_value(formatted: str, value: Any, crit_at: float, high_at: float,
               lower_is_worse: bool = True) -> str:
    """Wrap an already-formatted value in red/amber when it breaches thresholds."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return formatted
    if lower_is_worse:
        if v >= crit_at:
            return _hot(formatted, "#BA1A1A")
        if v >= high_at:
            return _hot(formatted, "#8A6100")
    else:
        if v <= crit_at:
            return _hot(formatted, "#BA1A1A")
        if v <= high_at:
            return _hot(formatted, "#8A6100")
    return formatted


def _cell_html(c: Any) -> str:
    """Table cell HTML: pre-formatted <font>/<b> values pass through, rest escaped.

    Pass RAW values here (single escape point). Pre-truncate with _trunc(),
    never with _t(), to avoid double-escaping.
    """
    s = "" if c is None else str(c)
    if s.lstrip().startswith("<font") or s.lstrip().startswith("<b>"):
        return s
    return _t(s, 240)


def _trunc(s: Any, n: int = 120) -> str:
    """Raw truncation without escaping (for cells escaped later by _cell_html)."""
    text = "" if s is None else str(s)
    text = text.replace("\n", " ").strip()
    if len(text) > n:
        text = text[: max(0, n - 1)] + "…"
    return text


def _callout(sev: str, title: str, text: str,
             styles: Dict[str, ParagraphStyle]) -> Table:
    """Tinted issue callout box with a bold severity bar — one per finding."""
    tag = {"critical": "CRITICAL", "high": "HIGH RISK",
           "medium": "WATCH", "good": "STRENGTH"}.get(sev, sev.upper())
    html = (f'<font color="{CALL_BAR.get(sev, PRIMARY).hexval()}"><b>{tag}</b></font>'
            f' &nbsp;—&nbsp; <b>{_e(title)}</b><br/><br/>{_e(text)}')
    t = Table([[Paragraph(html, styles["cell"])]], colWidths=[GRID_WIDTH * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CALL_BG.get(sev, ALT)),
        ("LINEBEFORE", (0, 0), (0, 0), 5, CALL_BAR.get(sev, PRIMARY)),
        ("BOX", (0, 0), (-1, -1), 0.5, CALL_BAR.get(sev, PRIMARY)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def _issue_callouts(issues: List[Dict[str, Any]], styles: Dict[str, ParagraphStyle],
                    engine: str | None = None, keyword: str | None = None,
                    limit: int = 3) -> List[Any]:
    """Pick the top findings for a section and render them as callout boxes."""
    sel = list(issues)
    if engine:
        sel = [i for i in sel if i.get("engine") == engine]
    if keyword:
        sel = [i for i in sel if keyword.lower() in
               (str(i.get("title", "")) + " " + str(i.get("detail", ""))).lower()]
    sel = sorted(sel, key=lambda i: SEV_RANK.get(i.get("sev", ""), 9))[:limit]
    out: List[Any] = []
    for i in sel:
        out.append(_callout(str(i.get("sev", "medium")),
                            str(i.get("title", ""))[:140],
                            str(i.get("detail", ""))[:280], styles))
        out.append(Spacer(1, 4))
    return out


def _kv_table(rows: List[List[str]], styles: Dict[str, ParagraphStyle]) -> Table:
    data = [[Paragraph(_t(k, 200), styles["cell"]), Paragraph(_t(v, 500), styles["cell"])]
            for k, v in rows]
    t = Table(data, colWidths=[58 * mm, (GRID_WIDTH - 58) * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (0, -1), ALT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _grid_table(header: List[str], rows: List[List[Any]], styles: Dict[str, ParagraphStyle],
                widths: List[float]) -> Table:
    total = round(sum(widths), 2)
    assert total == GRID_WIDTH, f"table widths sum to {total}, grid is {GRID_WIDTH}"
    data = [[Paragraph(_e(h), styles["cellh"]) for h in header]]
    for r in rows:
        data.append([Paragraph(_cell_html(c), styles["cell"]) for c in r])
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ALT]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    t.setStyle(TableStyle(style))
    return t


def _kpi_cards(cards: List[Tuple[str, str]], styles: Dict[str, ParagraphStyle]) -> Table:
    """Row of KPI cards; each card = big value over small label. 3 per row."""
    n = max(1, len(cards))
    col = GRID_WIDTH / n
    vals = [Paragraph(f"<b>{_e(v)}</b>", styles["kpi"]) for v, _ in cards]
    labs = [Paragraph(_e(l), styles["kpil"]) for _, l in cards]
    t = Table([vals, labs], colWidths=[col * mm] * n)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 1), (-1, 1), ALT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 1),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 2.5, PRIMARY),
    ]))
    return t


def _caption(text: str, styles: Dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(f"Figure — {_e(text)}", styles["caption"])


def _bar_drawing(title: str, labels: List[str], values: List[float],
                 vmax: float | None = None) -> Drawing:
    """Vertical bar chart locked to the 170 mm grid (482 pt)."""
    width_pt = GRID_WIDTH * mm  # 482.3
    d = Drawing(width_pt, 190)
    d.add(String(width_pt / 2, 178, title, fontName="Helvetica-Bold",
                 fontSize=9, fillColor=INK, textAnchor="middle"))
    bc = VerticalBarChart()
    bc.x = 38
    bc.y = 40
    bc.height = 125
    bc.width = width_pt - 60
    bc.data = [list(values)] if values else [[0]]
    top = max(values) if values else 0
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = (vmax if vmax else (top * 1.15 if top > 0 else 10))
    bc.valueAxis.valueStep = None
    bc.valueAxis.labels.fontSize = 7
    bc.valueAxis.labels.fillColor = MUTED
    bc.categoryAxis.labels.boxAnchor = "ne"
    bc.categoryAxis.labels.angle = 25
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.labels.fillColor = MUTED
    bc.categoryAxis.categoryNames = labels or ["—"]
    bc.bars[0].fillColor = PRIMARY
    bc.bars[0].strokeColor = PRIMARY_DARK
    bc.barLabelFormat = None
    bc.groupSpacing = 8
    d.add(bc)
    d.add(Line(38, 40, width_pt - 22, 40, strokeColor=LINE, strokeWidth=0.5))
    return d


def _pie_drawing(title: str, parts: List[Tuple[str, float]],
                 pie_colors: List[Any]) -> Drawing:
    width_pt = GRID_WIDTH * mm
    d = Drawing(width_pt, 175)
    d.add(String(width_pt / 2, 163, title, fontName="Helvetica-Bold",
                 fontSize=9, fillColor=INK, textAnchor="middle"))
    pie = Pie()
    pie.x = width_pt / 2 - 62
    pie.y = 22
    pie.width = 124
    pie.height = 124
    total = sum(v for _, v in parts) or 1
    pie.data = [v for _, v in parts]
    pie.labels = [f"{name} {_pct100(v / total * 100, 0)}" for name, v in parts]
    pie.slices.strokeWidth = 1
    pie.slices.strokeColor = colors.white
    pie.slices.fontSize = 7.5
    pie.slices.fontName = "Helvetica"
    pie.sideLabels = True
    for i, c in enumerate(pie_colors):
        pie.slices[i].fillColor = c
    d.add(pie)
    return d


def _empty_note(styles: Dict[str, ParagraphStyle], what: str) -> Paragraph:
    return Paragraph(f"No {what} recorded for this run.", styles["small"])


def render_report_pdf(data: Dict[str, Any], job_id: str, out_path: str) -> str:
    _ensure_pdf_deps()  # upgrade palette + bind reportlab (lazy, ~7MB only here)
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
    fresh = data.get("freshness", {}) or {}
    fsum = fresh.get("summary", {}) or {}
    adv = data.get("advanced", {}) or {}

    styles = _styles()
    brand = _e(cfg.get("target_brand", ""))
    brand_raw = str(cfg.get("target_brand", ""))
    brand_l = brand_raw.lower()

    verified = bool(di.get("verified"))
    try:
        score = float(di.get("verification_score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    models_real = bool(di.get("models_real"))
    if verified:
        badge = "VERIFIED"
    elif models_real and score >= 50:
        badge = "PARTIAL"
    else:
        badge = "UNVERIFIED"

    topics = cfg.get("industry_topics", []) or []
    comps = cfg.get("competitor_entities", []) or []
    n_topics, n_comp = len(topics), len(comps)
    inv_idx = cite.get("rag_invisibility_index")
    inv_composite = inv.get("composite_invisibility_index_pct")
    sov_composite = inv.get("composite_vector_share_of_voice_pct")

    vals_all = [r.get("proximity") for r in rows
                if isinstance(r.get("proximity"), (int, float))]
    avg_prox_all: Any = statistics.mean(vals_all) if vals_all else None
    ent_sum = cite.get("entity_summary", []) or []
    linked = sum(int(e.get("docs_linked", 0) or 0) for e in ent_sum)
    unlinked = sum(int(e.get("docs_unlinked", 0) or 0) for e in ent_sum)
    omitted = sum(int(e.get("docs_omitted", 0) or 0) for e in ent_sum)

    # ---- key findings (computed, never invented) ---------------------------
    per_topic = inv.get("per_topic", []) or []
    worst_topics = sorted(
        [r for r in per_topic if isinstance(r.get("topic_invisibility_pct"), (int, float))],
        key=lambda r: float(r.get("topic_invisibility_pct") or 0), reverse=True)[:3]
    best_topics = sorted(
        [r for r in per_topic if isinstance(r.get("topic_invisibility_pct"), (int, float))],
        key=lambda r: float(r.get("topic_invisibility_pct") or 0))[:3]
    agg: Dict[str, List[float]] = {}
    for r in rows:
        try:
            agg.setdefault(str(r.get("entity", "")), []).append(float(r.get("proximity")))
        except (TypeError, ValueError):
            continue
    leaderboard = sorted(((e, statistics.mean(v), len(v)) for e, v in agg.items() if v),
                         key=lambda x: -x[1])
    top_rival = next((x for x in leaderboard if x[0].lower() != brand_l), None)
    opts_all = cite.get("off_page_targets", []) or []
    top_target = opts_all[0] if opts_all else None

    # ---- run-global issues (single source with the web analysis) -----------
    try:
        from .issues import collect_issues as _collect_issues

        _issues = _collect_issues(data)
    except Exception:  # noqa: BLE001 — callouts must never break the PDF
        _issues = []

    # ---- doc with header rule + footer --------------------------------------
    def furniture(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(PRIMARY)
        canvas.setLineWidth(2)
        canvas.line(20 * mm, 281 * mm, 190 * mm, 281 * mm)
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
        topMargin=22 * mm, bottomMargin=20 * mm,
        title="RAG Corpus Entity & Vector Distance Auditor — Full Audit Report",
        author="ragevda",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=furniture)])

    el: List[Any] = []

    # ================= COVER ==================================================
    cover_rows = [
        [Paragraph("RAG CORPUS ENTITY &amp; VECTOR DISTANCE AUDITOR", styles["cover_sub"])],
        [Paragraph("Enterprise Audit Report", styles["cover_title"])],
        [Paragraph("Full analysis — 4 core engines · 6 RAG subfunctions · "
                   "poisoning &amp; engine-matrix extensions · complete outputs",
                   styles["cover_sub"])],
        [Paragraph(
            f"Target brand: <b>{brand}</b><br/>Generated: {_e(meta.get('generated_at', ''))}"
            f" &nbsp;|&nbsp; Job <b>{_e(job_id)}</b><br/>Corpus: "
            f"{_num(hs.get('fetched'))} fetched · {_num(cs.get('doc_count'))} clean docs · "
            f"{_num(n_topics)} topics · {_num(n_comp)} competitors",
            styles["cover_meta"])],
        [Paragraph(f"{badge} &nbsp;·&nbsp; verification {_r(di.get('verification_score'))}/100",
                   styles["cover_badge"])],
    ]
    cover = Table(cover_rows, colWidths=[GRID_WIDTH * mm])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COVER_BG),
        ("LINEBELOW", (0, 0), (-1, -2), 1, colors.HexColor("#3B383E")),
        ("LINEBELOW", (0, -1), (-1, -1), 3, COVER_RULE),
        ("BACKGROUND", (0, -1), (-1, -1), PRIMARY_DARK),
        ("TOPPADDING", (0, 0), (-1, 0), 14),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 2),
        ("TOPPADDING", (0, 2), (-1, 2), 2),
        ("BOTTOMPADDING", (0, 2), (-1, 2), 6),
        ("TOPPADDING", (0, 3), (-1, 3), 6),
        ("BOTTOMPADDING", (0, 3), (-1, 3), 8),
        ("TOPPADDING", (0, -1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    el.append(cover)
    el.append(Spacer(1, 8))
    el.append(_kpi_cards([
        (_r(inv_idx), "RAG INVISIBILITY INDEX — lower is better"),
        (_pct100(sov_composite), "VECTOR SHARE OF VOICE"),
        (_r(avg_prox_all), "MEAN VECTOR PROXIMITY"),
    ], styles))
    el.append(Spacer(1, 4))
    el.append(_kpi_cards([
        (_num(len(rows)), "PROXIMITY COMPARISONS"),
        (_num(len(recs)), "PRIORITIZED RECOMMENDATIONS"),
        (f"{badge} {_r(di.get('verification_score'))}", "VERIFICATION / 100"),
    ], styles))
    el.append(Spacer(1, 4))
    el.append(Paragraph(
        "How to read this report: §1 states the verdict in one page. §2 lists every "
        "input the run executed. §3 proves the evidence is real. §§4–5 detail the four "
        "core engines. §§6–11 detail the six RAG subfunctions. §12 covers poisoning and "
        "per-AI-engine visibility. §§13–14 publish the complete output tables. Figures "
        "are captioned with their method; tables repeat headers across pages.",
        styles["small"]))

    # ================= 1 EXECUTIVE SUMMARY =====================================
    el.append(_section_band("1", "Executive Summary — Verdict in One Page", styles))
    el.append(Paragraph(
        f"This audit harvested <b>{_num(hs.get('fetched'))}</b> web documents "
        f"(<b>{_num(cs.get('doc_count'))}</b> after cleanroom parsing) for <b>{brand}</b> "
        f"across <b>{n_topics}</b> topics and <b>{n_comp}</b> competitors, embedded locally "
        f"with <b>{_e(meta.get('embedding_kind', ''))}</b> and parsed with "
        f"<b>{_e(meta.get('ner_kind', ''))}</b>. The brand's <b>RAG Invisibility Index is "
        f"{_r(inv_idx)}</b> ({_pct100(inv_composite)} composite): that share of high-ranking "
        f"industry passages cites competitors while omitting the brand entirely. Its "
        f"<b>vector share of voice is {_pct100(sov_composite)}</b> at a mean proximity of "
        f"<b>{_r(avg_prox_all)}</b> over <b>{_num(len(rows))}</b> topic × entity comparisons "
        f"(<b>{_num(linked)}</b> linked · <b>{_num(unlinked)}</b> unlinked · "
        f"<b>{_num(omitted)}</b> omitted mentions). Evidence integrity scores "
        f"<b>{_r(di.get('verification_score'))}/100 ({badge})</b> with "
        f"{_pct100(fsum.get('live_pct'))} live sources.",
        styles["body"]))
    findings: List[str] = []
    if worst_topics:
        findings.append("Blind spots (highest invisibility): " + "; ".join(
            f"{r.get('topic')} ({_pct100(r.get('topic_invisibility_pct'))})" for r in worst_topics))
    if best_topics:
        findings.append("Strongholds (lowest invisibility): " + "; ".join(
            f"{r.get('topic')} ({_pct100(r.get('topic_invisibility_pct'))})" for r in best_topics))
    if top_rival:
        findings.append(f"Closest rival in vector space: {top_rival[0]} "
                        f"(mean proximity {_r(top_rival[1])} across {top_rival[2]} topics)")
    if top_target:
        findings.append(f"Highest-value off-page target: {(top_target.get('title') or top_target.get('url'))} "
                        f"(relevance {_r(top_target.get('topic_relevance'))})")
    dr0 = (adv.get("drift", {}) or {})
    if dr0.get("alerts"):
        findings.append(f"{len(dr0['alerts'])} semantic-drift alerts vs the prior run — see §7.")
    else:
        findings.append("Drift baseline snapshotted — the next scheduled run will produce true deltas.")
    for f in findings:
        el.append(Paragraph(f"• &nbsp;{_t(f, 400)}", styles["bullet"]))
    el.append(Paragraph("Top issues — read these first", styles["h3"]))
    el.append(Paragraph(
        "Every red or amber box in this report is a computed finding, not an "
        "opinion. The four below are the highest-severity items in this run.",
        styles["small"]))
    for item in _issue_callouts(_issues, styles, limit=4):
        el.append(item)
    el.append(Paragraph("30-day action plan (highest leverage first)", styles["h3"]))
    for r in recs[:5]:
        el.append(Paragraph(
            f"<b>[{_e(r.get('priority'))}] {_t(r.get('title'), 140)}</b> — "
            f"{_t(r.get('rationale', r.get('detail', '')), 260)}", styles["bullet"]))
    if not recs[:5]:
        el.append(_empty_note(styles, "recommendations"))

    # ================= 2 CONTENTS ===============================================
    el.append(_section_band("2", "Contents", styles))
    for item in [
        "3. Audit Inputs — all 11 enterprise fields actually executed",
        "4. Methodology &amp; Verification — models, harvest, freshness, support, provenance",
        "5. Core micro-engines 1–4 — harvester · embeddings · NER graphs · citation gaps",
        "6. Subfunction 5 — Chunking &amp; Contextual-Window Simulator",
        "7. Subfunction 6 — Semantic Drift Tracking &amp; Time-Series DB",
        "8. Subfunction 7 — Local LLM Summarization &amp; Gap Analysis",
        "9. Subfunction 8 — RAG Chunk Hallucination &amp; Sentiment Auditor",
        "10. Subfunction 9 — Synthetic Query Generator (reverse-engineered RAG prompts)",
        "11. Subfunction 10 — Automated Token-Density Adjuster",
        "12. Enterprise extensions — vector-poisoning audit + engine-matrix SoV heatmap",
        "13. Per-topic invisibility &amp; share-of-voice ledger",
        "14. Outputs — proximity · citation ledger · off-page targets · action plan · provenance",
        "Appendix A. Topic relevance thresholds &amp; methods glossary",
    ]:
        el.append(Paragraph(f"• &nbsp;{item}", styles["toc"]))

    # ================= 3 INPUTS ==================================================
    el.append(_section_band("3", "Audit Inputs — All 11 Enterprise Fields", styles))
    el.append(Paragraph(
        "Exactly what this run executed against. Re-run with edited values to extend "
        "the trend in History &amp; Trends.", styles["small"]))
    qt = cfg.get("query_templates", {}) or {}
    ew = cfg.get("entity_weighting", {}) or {}
    onto = cfg.get("ontology_aliases", {}) or {}
    sfoot = cfg.get("serp_footprints", []) or []
    feeds = cfg.get("content_feeds", []) or []
    cfiles = cfg.get("corpus_files", []) or []
    el.append(_kv_table([
        ["01 · Target brand", brand],
        ["02 · Industry topics", ", ".join(_t(x, 300) for x in topics)],
        ["03 · Competitor entities", ", ".join(_t(x, 300) for x in comps)],
        ["04 · Crawl depth", f'{_num(cfg.get("crawl_depth"))} pages / results per query'],
        ["05 · Locality", _e(cfg.get("locality") or "global")],
        ["06 · Search intent", _e(cfg.get("search_intent", ""))],
        ["06b · Query templates", "; ".join(f'{_t(k, 40)}: {_t(v, 90)}'
                                            for k, v in list(qt.items())[:16]) or "—"],
        ["07 · Entity weighting", "; ".join(f"{_t(k, 40)}={_t(v, 20)}"
                                            for k, v in list(ew.items())[:16]) or "—"],
        ["07b · Ontology aliases", "; ".join(
            f"{_t(k, 40)}: {', '.join(_t(a, 40) for a in (v or [])[:6])}"
            for k, v in list(onto.items())[:10]) or "—"],
        ["08 · Ground-truth files", "; ".join(_t(x, 120) for x in cfiles[:8]) or "—"],
        ["08b · Ground-truth dir", _e(cfg.get("corpus_dir") or "—")],
        ["09 · Embedding model", _e(cfg.get("embedding_model", ""))],
        ["09b · spaCy / sentiment",
         f'{_e(cfg.get("spacy_model", ""))} / {_e(di.get("sentiment_model", ""))}'],
        ["10 · SERP footprints", "; ".join(_t(x, 130) for x in sfoot[:8]) or "—"],
        ["11 · Content feeds", "; ".join(_t(x, 120) for x in feeds[:8]) or "—"],
        ["Tuning · harvester",
         f'{_e(cfg.get("harvester", ""))} (prefer SearXNG: '
         f'{"yes" if cfg.get("prefer_searxng") else "no"}; '
         f'SearXNG: {_e(cfg.get("searxng_base_url") or "—")})'],
        ["Tuning · AI-engine matrix",
         ", ".join(_t(x, 60) for x in (cfg.get("engine_matrix", []) or [])) or "—"],
        ["Tuning · chunks",
         f'{_num(cfg.get("chunk_tokens"))} tokens / {_num(cfg.get("chunk_overlap_tokens"))} '
         f'overlap / top-{_num(cfg.get("top_k_retrieval"))} retrieval'],
        ["Tuning · density / synthetic",
         f'target density {_r(cfg.get("target_entity_density"))} · '
         f'{_num(cfg.get("synthetic_query_count"))} synthetic queries'],
        ["Tuning · Ollama",
         f'{_e(cfg.get("ollama_model") or "—")} @ {_e(cfg.get("ollama_base_url") or "—")}'],
    ], styles))

    # ================= 4 VERIFICATION ============================================
    el.append(_section_band("4", "Methodology &amp; Verification", styles))
    el.append(_kv_table([
        ["Embedding engine",
         f'{_e(meta.get("embedding_kind", ""))} ({_e(meta.get("embedding_model", ""))})'],
        ["NER engine", f'{_e(meta.get("ner_kind", ""))} ({_e(meta.get("ner_model", ""))})'],
        ["Sentiment model", _e(di.get("sentiment_model", ""))],
        ["Real models (no synthetic fallback)", "yes" if di.get("models_real") else "no"],
        ["Harvest succeeded", "yes" if di.get("harvest_ok") else "no"],
        ["Documents harvested", _num(di.get("harvested_docs"))],
        ["Near-duplicates removed", _num(di.get("dedup_removed"))],
        ["Entities with mentions",
         f'{_num(di.get("entities_with_mentions"))} / {_num(di.get("entities_total"))}'],
        ["Provenance complete", "yes" if di.get("provenance_complete") else "partial"],
        ["Support fraction", _pct(di.get("support_fraction"))],
        ["Sub-scores (models / harvest / support / provenance / live)",
         " / ".join([_r(di.get("models_real_score")), _r(di.get("harvest_ok_score")),
                     _r(di.get("support_score")), _r(di.get("provenance_score")),
                     _r(di.get("live_score"))])],
        ["Freshness",
         f'grade {_e(fsum.get("freshness_grade"))} · composite {_r(fsum.get("freshness_composite"))} · '
         f'live {_pct100(fsum.get("live_pct"))} · fresh {_pct100(fsum.get("fresh_pct"))} · '
         f'stale {_pct100(fsum.get("stale_pct"))} · median age {_r(fsum.get("median_age_days"))} d · '
         f'p90 {_r(fsum.get("p90_age_days"))} d · p95 {_r(fsum.get("p95_age_days"))} d · '
         f'{_num(fsum.get("total_sources"))} sources'],
        ["Verification score", f'{_r(di.get("verification_score"))} / 100  ({badge})'],
    ], styles))
    el.append(Spacer(1, 4))
    el.append(Paragraph(
        "Scores derive from live harvested content and local model inference. Semantic "
        "proximity and NER are model-derived estimates; verification confirms provenance, "
        "model authenticity and corpus integrity — not the factual truth of third-party pages.",
        styles["small"]))

    # ================= 5 CORE ENGINES =============================================
    el.append(_section_band("5", "Core Micro-Engines 1–4", styles))
    engines = [
        ("Engine 1 · Zero-Cost Headless Web Harvester",
         "DuckDuckGo / SearXNG / Playwright pull top pages, Reddit threads and news; "
         "BeautifulSoup / trafilatura cleanroom parsing isolates the indexable body text "
         "a RAG crawler actually ingests.",
         [f'{_num(hs.get("queries"))} queries', f'{_num(hs.get("fetched"))} pages fetched',
          f'{_num(hs.get("dedup_removed"))} duplicates removed', f'{_num(cs.get("doc_count"))} clean docs']),
        ("Engine 2 · Local Vector Embedding &amp; Semantic Mapping",
         f"Paragraphs, brand and competitors projected into one vector space with "
         f"{_e(cfg.get('embedding_model', ''))}; exact cosine similarity "
         f"(0.00 unrelated → 1.00 identical).",
         [f'{_e(meta.get("embedding_kind", ""))}', f'{_num(len(rows))} comparisons',
          f'mean proximity {_r(avg_prox_all)}']),
        ("Engine 3 · Local NER &amp; Knowledge Graphs",
         f"spaCy ({_e(cfg.get('spacy_model', ''))}) extracts ORG / PRODUCT / PERSON; "
         f"networkx co-occurrence graphs measure brand vs rival topical proximity.",
         [f'{_e(meta.get("ner_kind", ""))}', f'{_num(di.get("entities_total"))} entities',
          f'{_num(len(ent_sum))} audited']),
        ("Engine 4 · Unlinked Authority &amp; Citation Gap Finder",
         "Each article classified linked / unlinked-mention / omitted per entity — "
         "the signal behind the Invisibility Index and the off-page target list.",
         [f'invisibility {_r(inv_idx)}', f'{_num(cite.get("high_relevance_doc_count"))} high-rel docs',
          f'{_num(linked)} linked / {_num(unlinked)} unlinked / {_num(omitted)} omitted']),
    ]
    for title, desc, chips in engines:
        el.append(Paragraph(title, styles["h3"]))
        el.append(Paragraph(desc, styles["body"]))
        el.append(Paragraph(
            f'<font color="{PRIMARY_HEX}"><b>{" &nbsp;•&nbsp; ".join(_t(c, 120) for c in chips)}</b></font>',
            styles["small"]))
        el.append(Spacer(1, 4))
    el.append(Paragraph("Engine issues flagged in this run", styles["h3"]))
    for item in _issue_callouts(_issues, styles, engine="vector_embedding", limit=2):
        el.append(item)
    # charts: proximity buckets + citation pie
    buckets = {"Tight (≥0.70)": 0, "Close (≥0.50)": 0, "Moderate (≥0.35)": 0, "Far (<0.35)": 0}
    for r in rows:
        try:
            v = float(r.get("proximity"))
        except (TypeError, ValueError):
            continue
        if v >= 0.70:
            buckets["Tight (≥0.70)"] += 1
        elif v >= 0.50:
            buckets["Close (≥0.50)"] += 1
        elif v >= 0.35:
            buckets["Moderate (≥0.35)"] += 1
        else:
            buckets["Far (<0.35)"] += 1
    el.append(_bar_drawing("Comparison volume by proximity band (n=%d)" % len(vals_all),
                           list(buckets.keys()), list(buckets.values())))
    el.append(_caption("Cosine-similarity histogram over all topic × entity comparisons. "
                       "A healthy profile concentrates brand rows in Tight/Close.", styles))
    el.append(_pie_drawing("Brand + rival mentions: linked vs unlinked vs omitted",
                           [("Linked", linked), ("Unlinked", unlinked), ("Omitted", omitted)],
                           [GOOD, WARN, BAD]))
    el.append(_caption("Citation ledger totals across audited entities. Unlinked rows are "
                       "outreach targets; omitted rows are content-gap targets.", styles))

    # ================= 6 CHUNKING ==================================================
    ch = adv.get("chunking", {}) or {}
    el.append(_section_band("6", "Subfunction 5 · Chunking &amp; Contextual-Window Simulator", styles))
    el.append(Paragraph(
        "RAG engines retrieve 256–512 token chunks, never whole pages. Scoring full-page "
        "vectors would create false positives, so this run split every page into real "
        "retrieval windows before embedding.", styles["body"]))
    el.append(_kv_table([
        ["Token windows", _num(ch.get("window_count"))],
        ["Top-k retrieved", _num(ch.get("retrieved_count"))],
        ["Tokens processed", _num(ch.get("tokens_processed"))],
        ["Chunk size / overlap",
         f'{_num(ch.get("chunk_tokens"))} / {_num(ch.get("chunk_overlap_tokens"))} tokens'],
    ], styles))
    per_doc = ch.get("per_doc_windows", {}) or ch.get("windows_by_doc", {}) or {}
    if isinstance(per_doc, dict) and per_doc:
        top_docs = sorted(
            per_doc.items(),
            key=lambda kv: (len(kv[1]) if isinstance(kv[1], list)
                            else int(kv[1] or 0)),
            reverse=True)[:10]
        el.append(_grid_table(["Document", "Windows"],
                              [[_trunc(k, 140), _num(len(v) if isinstance(v, list) else v)]
                               for k, v in top_docs], styles, [130.0, 40.0]))

    # ================= 7 DRIFT ======================================================
    dr = adv.get("drift", {}) or {}
    el.append(_section_band("7", "Subfunction 6 · Semantic Drift Tracking &amp; Time-Series DB", styles))
    el.append(Paragraph(
        "AI search re-indexes continuously and vector positions move. Each run snapshots "
        f"metrics into {_t(dr.get('db_path', 'drift_timeseries.duckdb'), 120)} and diffs "
        "against the prior run — the daily/weekly answer to “did we drift after a "
        "competitor launch?”.", styles["body"]))
    el.append(_kv_table([
        ["Topics tracked", _num(len(dr.get("per_topic", []) or []))],
        ["Drift alerts", _num(len(dr.get("alerts", []) or []))],
        ["Tolerance", _e(dr.get("drift_tolerance", ""))],
        ["Store available", "yes" if dr.get("store_available") else "no"],
    ], styles))
    drift_all = dr.get("per_topic", []) or []
    for item in _issue_callouts(_issues, styles, engine="drift_tracking", limit=3):
        el.append(item)
    drift_rows = [[r.get("topic"), _r(r.get("proximity")), _pct100(r.get("invisibility_pct")),
                   _pct100(r.get("sov_pct")), _r(r.get("proximity_delta")),
                   _r(r.get("invisibility_delta")), _r(r.get("sov_delta")),
                   "prior" if r.get("has_prior") else "baseline"]
                  for r in drift_rows_sort(drift_all)[:30]]
    if drift_rows:
        el.append(_grid_table(
            ["Topic", "Prox", "Invis", "SoV", "Δprox", "Δinvis", "ΔSoV", "Base"],
            drift_rows, styles, [52.0, 18.0, 18.0, 18.0, 18.0, 18.0, 18.0, 10.0]))
    else:
        el.append(_empty_note(styles, "drift rows"))
    for a in (dr.get("alerts", []) or [])[:10]:
        el.append(Paragraph(f" {_t(a.get('topic', ''), 60)} — "
                            f"{_t(a.get('message', a.get('detail', '')), 200)}", styles["body"]))

    # ================= 8 LLM =========================================================
    llm = adv.get("llm", {}) or {}
    el.append(_section_band("8", "Subfunction 7 · Local LLM Summarization &amp; Gap Analysis", styles))
    el.append(Paragraph(
        "Ollama (Mistral / Llama 3) reads the retrieved chunks locally and answers “why "
        "did the retriever prefer the competitor here?” as explicit brief guidance — "
        "no paid APIs, raw math turned into assignments.", styles["body"]))
    el.append(_kv_table([
        ["LLM available", "yes" if llm.get("available") else "no — deterministic metrics only"],
        ["Model", _e(llm.get("model") or "—")],
        ["Note", _t(llm.get("note", ""), 400)],
    ], styles))
    for r in (llm.get("rationale", []) or [])[:10]:
        if isinstance(r, dict):
            el.append(Paragraph(
                f"• <b>{_t(r.get('topic', r.get('title', '')), 80)}</b> — "
                f"{_t(r.get('text', r.get('rationale', '')), 300)}", styles["bullet"]))
        else:
            el.append(Paragraph(f"• {_t(r, 350)}", styles["bullet"]))

    # ================= 9 SENTIMENT ====================================================
    sent = adv.get("sentiment", {}) or {}
    el.append(_section_band("9", "Subfunction 8 · Hallucination &amp; Sentiment Auditor", styles))
    el.append(Paragraph(
        "Visibility without framing control is liability. Every mention window is scored "
        "for sentiment polarity; negatively framed retrieval windows are flagged verbatim "
        "as brand-sentiment risks for neutralization.", styles["body"]))
    el.append(_kv_table([
        ["Method / model",
         f'{_t(sent.get("method", ""), 160)} / {_t(sent.get("model", di.get("sentiment_model", "")), 120)}'],
        ["Entities audited", _num(len(sent.get("per_entity", []) or []))],
        ["Risk windows", _num(len(sent.get("risk_windows", []) or []))],
    ], styles))
    per_ent = sent.get("per_entity", []) or []
    for item in _issue_callouts(_issues, styles, engine="sentiment", limit=3):
        el.append(item)
    brand_sent = next((s for s in per_ent if str(s.get("entity", "")).lower() == brand_l), None)
    if brand_sent:
        try:
            el.append(_pie_drawing(
                f"Framing of “{brand_raw}” mentions (n={brand_sent.get('mentions')})",
                [("Positive", float(brand_sent.get("positive_pct") or 0)),
                 ("Neutral", float(brand_sent.get("neutral_pct") or 0)),
                 ("Negative", float(branch_neg(brand_sent)))],
                [GOOD, SECONDARY, BAD]))
            el.append(_caption("Share of brand mention-windows by polarity. Negative slices "
                               "are quoted verbatim below.", styles))
        except (TypeError, ValueError):
            pass
    sent_rows = [[r.get("entity"),
                 _sev_value(_r(r.get("net_sentiment")), r.get("net_sentiment"),
                            0.0, 0.15, lower_is_worse=False),
                 f'{_pct100(r.get("positive_pct"))} / {_pct100(r.get("neutral_pct"))} / '
                 f'{_pct100(r.get("negative_pct"))}',
                 _hot(_num(r.get("risk_windows")), "#BA1A1A")
                 if int(r.get("risk_windows", 0) or 0) > 0 else _num(r.get("risk_windows")),
                 _trunc(r.get("framing", ""), 60)]
                for r in per_ent[:15]]
    if sent_rows:
        el.append(_grid_table(["Entity", "Net sent.", "Pos / Neu / Neg", "Risks", "Framing"],
                              sent_rows, styles, [44.0, 22.0, 52.0, 18.0, 34.0]))
    else:
        el.append(_empty_note(styles, "sentiment rows"))
    rw = (sent.get("risk_windows", []) or [])[:10]
    if rw:
        el.append(Paragraph("Flagged risk windows — verbatim evidence", styles["h3"]))
        el.append(_grid_table(["Entity", "Source", "Polarity", "Snippet"],
                              [[r.get("entity"), _trunc(r.get("title") or r.get("url"), 70),
                                _hot(_r(r.get("polarity")), "#BA1A1A"), _trunc(r.get("snippet"), 160)]
                               for r in rw], styles, [28.0, 50.0, 18.0, 74.0]))

    # ================= 10 SYNTHETIC ====================================================
    syn = adv.get("synthetic_queries", {}) or {}
    el.append(_section_band("10", "Subfunction 9 · Synthetic Query Generator", styles))
    el.append(Paragraph(
        "Competitor chunks are reverse-engineered into the exact synthetic prompts an AI "
        "engine would issue to retrieve them. Brand-targeted variants become Q&A / FAQ "
        f"content targets. {_t(syn.get('note', ''), 300)}", styles["body"]))
    syn_rows: List[List[Any]] = []
    for ent, qs in (syn.get("per_entity", {}) or {}).items():
        for q in (qs or [])[:4]:
            if isinstance(q, dict):
                syn_rows.append([ent, q.get("query"), q.get("topic"),
                                 q.get("type"), _r(q.get("retrieval_confidence"))])
            else:
                syn_rows.append([ent, q, "", "", ""])
            if len(syn_rows) >= 20:
                break
        if len(syn_rows) >= 20:
            break
    if syn_rows:
        el.append(_grid_table(["Entity", "Synthetic prompt", "Topic", "Type", "Conf."],
                              syn_rows, styles, [30.0, 62.0, 34.0, 24.0, 20.0]))
    else:
        el.append(_empty_note(styles, "synthetic queries"))

    # ================= 11 DENSITY =======================================================
    td = adv.get("token_density", {}) or {}
    el.append(_section_band("11", "Subfunction 10 · Automated Token-Density Adjuster", styles))
    el.append(Paragraph(
        f"On-window brand vs leader token density per topic, with the precise token budget "
        f"to displace the leader from top-{_num(cfg.get('top_k_retrieval'))} retrieval. "
        f"{_t(td.get('method', ''), 250)} Readiness: "
        f"<b>{_t(td.get('brand_displacement_readiness', ''), 40)}</b> · windows analyzed: "
        f"<b>{_num(td.get('windows_analyzed'))}</b>.", styles["body"]))
    td_all = td.get("per_topic", []) or []
    for item in _issue_callouts(_issues, styles, engine="token_density", limit=2):
        el.append(item)
    td_rows = [[r.get("topic"), r.get("leading_competitor"),
               _sev_value(_num(r.get("tokens_needed_to_displace")),
                          r.get("tokens_needed_to_displace"), 50, 30),
               _r(r.get("brand_density")),
               _r(r.get("leader_density")), _trunc(r.get("severity", ""), 40)]
              for r in td_all[:30]]
    if td_rows:
        el.append(_grid_table(["Topic", "Leader", "Tokens to displace", "Brand dens.",
                               "Leader dens.", "Severity"],
                              td_rows, styles, [46.0, 30.0, 30.0, 22.0, 22.0, 20.0]))
        el.append(Paragraph("Displacement actions — how to win each topic", styles["h3"]))
        for r in td_all[:8]:
            if r.get("action"):
                el.append(Paragraph(f"• <b>{_t(r.get('topic'), 70)}</b> — "
                                    f"{_t(r.get('action'), 350)}", styles["bullet"]))
    else:
        el.append(_empty_note(styles, "token-density rows"))

    # ================= 12 EXTENSIONS =====================================================
    pois = adv.get("poisoning", {}) or {}
    el.append(_section_band("12", "Extensions · Poisoning Audit + Engine-Matrix SoV", styles))
    el.append(Paragraph(
        "Low-quality co-citations drag the brand centroid toward junk topics. Spam "
        "templates, path stuffing and thin pages are machine-scored so they never "
        "masquerade as editorial authority. The engine matrix then maps every topic "
        "against each AI surface — dominance on one engine never implies visibility "
        "on another.", styles["body"]))
    el.append(_kv_table([
        ["Brand poisoning status", _e(pois.get("brand_poisoning_status", ""))],
        ["Brand machine / repetition",
         f'{_r(pois.get("brand_machine_score"))} / {_r(pois.get("brand_repetition_score"))}'],
        ["Generated-phrase hits (brand)", _num(pois.get("brand_generated_phrase_hits"))],
        ["Toxic / total sources",
         f'{_num(pois.get("toxic_source_count"))} / {_num(pois.get("total_sources"))}'],
        ["Method", _t(pois.get("method", ""), 300)],
    ], styles))
    for item in _issue_callouts(_issues, styles, keyword="poison", limit=2):
        el.append(item)
    for item in _issue_callouts(_issues, styles, keyword="toxic", limit=1):
        el.append(item)
    psrc = sorted((pois.get("sources", []) or []),
                  key=lambda s: float((s or {}).get("poisoning_risk") or 0), reverse=True)[:12]
    if psrc:
        el.append(Paragraph("Highest-risk sources", styles["h3"]))
        el.append(_grid_table(["Domain", "Risk", "Machine", "Why flagged"],
                              [[_trunc(s.get("domain"), 60),
                                _sev_value(_r(s.get("poisoning_risk")), s.get("poisoning_risk"),
                                           0.7, 0.4),
                                _r(s.get("machine_score")), _trunc(s.get("risk_factors"), 120)]
                               for s in psrc], styles, [52.0, 20.0, 20.0, 78.0]))
    em = adv.get("engine_matrix", {}) or {}
    ecomp = em.get("engine_composite", []) or []
    if ecomp:
        el.append(Paragraph("Engine-composite share of voice", styles["h3"]))
        el.append(_bar_drawing(
            "Brand SoV by AI surface — composite % (evidence-weighted)",
            [short_engine(r.get("engine")) for r in ecomp],
            [float(r.get("composite_sov_pct") or 0) for r in ecomp], vmax=100))
        el.append(_caption("One bar per AI surface in the configured engine matrix. Gaps "
                           "between bars are platform-specific content opportunities.", styles))
        el.append(_grid_table(["AI engine", "Composite SoV", "Evidence docs"],
                              [[r.get("engine"), _pct100(r.get("composite_sov_pct")),
                                _num(r.get("evidence_docs"))] for r in ecomp],
                              styles, [70.0, 50.0, 50.0]))
        el.append(Paragraph(f"Method: {_t(em.get('method', ''), 350)}", styles["small"]))
    cells = sorted((em.get("cells", []) or []),
                   key=lambda c: int((c or {}).get("relevant_docs") or 0), reverse=True)[:20]
    if cells:
        el.append(Paragraph("Top topic × engine cells (by evidence)", styles["h3"]))
        el.append(_grid_table(["Topic", "Engine", "Vector SoV", "Docs", "Conf."],
                              [[c.get("topic"), c.get("engine"), _pct100(c.get("vector_sov_pct")),
                                _num(c.get("relevant_docs")), _r(c.get("confidence"))]
                               for c in cells], styles, [52.0, 44.0, 26.0, 20.0, 28.0]))

    # ---- per-topic invisibility chart + ledger --------------------------------------------
    el.append(_section_band("13", "Per-Topic Invisibility &amp; Share-of-Voice Ledger", styles))
    el.append(Paragraph(
        "Per topic: relevant docs, brand vs rival presence, invisibility % and vector "
        "share of voice. Sort target: high invisibility × high relevance.", styles["body"]))
    inv_sorted = sorted(
        per_topic,
        key=lambda r: (int(r.get("relevant_docs") or 0)
                       * float(r.get("topic_invisibility_pct") or 0)),
        reverse=True)
    top10 = inv_sorted[:10]
    if top10:
        el.append(_bar_drawing(
            "Top 10 priority topics by invisibility % (bar) — relevance-weighted order",
            [_t(r.get("topic"), 14) for r in top10],
            [float(r.get("topic_invisibility_pct") or 0) for r in top10], vmax=100))
        el.append(_caption("Invisibility % per priority topic. Pair with the ledger below: "
                           "high bars with many relevant docs are quarter-one targets.", styles))
    inv_rows = [[r.get("topic"), _num(r.get("relevant_docs")), _num(r.get("brand_present_docs")),
                 _num(r.get("competitor_present_docs")),
                 _sev_value(_pct100(r.get("topic_invisibility_pct")),
                            r.get("topic_invisibility_pct"), 70, 40),
                 _sev_value(_pct100(r.get("vector_share_of_voice_pct")),
                            r.get("vector_share_of_voice_pct"), 20, 35,
                            lower_is_worse=False),
                 _r(r.get("threshold_used"))]
                for r in inv_sorted[:40]]
    for item in _issue_callouts(_issues, styles, engine="citation_gap", limit=3):
        el.append(item)
    if inv_rows:
        el.append(_grid_table(["Topic", "Rel docs", "Brand", "Rivals", "Invis", "SoV", "Thresh"],
                              inv_rows, styles, [56.0, 20.0, 18.0, 18.0, 20.0, 20.0, 18.0]))
    else:
        el.append(_empty_note(styles, "per-topic rows"))

    # ================= 14 OUTPUTS ===========================================================
    el.append(_section_band("14", "Outputs — Complete Results", styles))
    el.append(Paragraph(
        f"RAG Invisibility Index <b>{_r(inv_idx)}</b> — the share of high-ranking passages "
        f"where {brand} is absent while rivals are co-cited. Lower is better.",
        styles["body"]))
    el.append(Paragraph("14.1 Semantic vector proximity — full table (brand-first, top 40)",
                        styles["h3"]))
    rows_sorted = sorted(rows, key=lambda r: (
        0 if str(r.get("entity", "")).lower() == brand_l else 1,
        -(float(r.get("proximity")) if isinstance(r.get("proximity"), (int, float)) else 0.0)))
    prox_rows = []
    for r in rows_sorted[:40]:
        lab = str(r.get("label", ""))
        is_brand = str(r.get("entity", "")).lower() == brand_l and brand_l
        prox_cell = _r(r.get("proximity"))
        lab_cell = lab
        if is_brand and ("far" in lab.lower() or "unrelated" in lab.lower()):
            prox_cell = _hot(prox_cell, "#8A6100")
            lab_cell = _hot(_e(lab), "#8A6100")
        prox_rows.append([r.get("topic"), r.get("entity"), prox_cell,
                          lab_cell, _num(r.get("docs_highly_relevant"))])
    if prox_rows:
        el.append(_grid_table(["Topic", "Entity", "Proximity", "Label", "High-rel docs"],
                              prox_rows, styles, [52.0, 40.0, 22.0, 32.0, 24.0]))
    else:
        el.append(_empty_note(styles, "proximity rows"))

    el.append(Paragraph("14.2 Entity citation ledger — linked / unlinked / omitted", styles["h3"]))
    cite_rows = [[e.get("entity"), _num(e.get("docs_total")), _num(e.get("docs_mentioned")),
                 _num(e.get("docs_linked")), _num(e.get("docs_unlinked")),
                 _num(e.get("docs_omitted")), _pct100(e.get("mention_rate_pct"))]
                for e in ent_sum[:20]]
    if cite_rows:
        el.append(_grid_table(["Entity", "Docs", "Mentioned", "Linked", "Unlinked", "Omitted", "Mention %"],
                              cite_rows, styles, [34.0, 18.0, 22.0, 18.0, 20.0, 18.0, 40.0]))
    else:
        el.append(_empty_note(styles, "citation rows"))

    el.append(Paragraph("14.3 High-density off-page targets (top 20)", styles["h3"]))
    opt_rows = [[(t.get("title") or t.get("url")), t.get("source_type"),
                 t.get("top_topic"), _r(t.get("topic_relevance")), _num(t.get("competitors_present"))]
                for t in opts_all[:20]]
    if opt_rows:
        el.append(_grid_table(["URL / Title", "Type", "Top topic", "Relevance", "Competitors"],
                              opt_rows, styles, [70.0, 22.0, 36.0, 22.0, 20.0]))
    else:
        el.append(_empty_note(styles, "off-page targets"))

    el.append(Paragraph("14.4 Actionable recommendations (top 20, with rationale)", styles["h3"]))
    def _pri_cell(p: Any) -> str:
        s = "" if p is None else str(p)
        low = s.lower()
        if "p0" in low or "critical" in low:
            return _hot(_e(s), "#BA1A1A")
        if "p1" in low or "high" in low:
            return _hot(_e(s), "#8A6100")
        return s
    rec_rows = [[_pri_cell(r.get("priority")),
                 _trunc(f"{r.get('title') or ''} — "
                        f"{r.get('rationale', r.get('detail', '')) or ''}", 260),
                 r.get("category"), _r(r.get("score"))]
                for r in recs[:20]]
    if rec_rows:
        el.append(_grid_table(["Priority", "Directive + rationale", "Category", "Score"],
                              rec_rows, styles, [18.0, 92.0, 34.0, 26.0]))
    else:
        el.append(_empty_note(styles, "recommendations"))

    el.append(Paragraph("14.5 Provenance — audited sources (sample 20 of "
                        f"{_num(len(prov))})", styles["h3"]))
    el.append(Paragraph(
        "Each URL was fetched live; status, timing, content hash and freshness are read "
        "verbatim from the HTTP response. The complete ledger ships in report.json / "
        "sources.csv.", styles["small"]))
    prov_rows = [[p.get("domain"), p.get("top_topic"), _r(p.get("top_topic_relevance")),
                 p.get("http_status"), p.get("staleness"),
                 "live" if p.get("live") else "—"]
                for p in prov[:20]]
    if prov_rows:
        el.append(_grid_table(["Domain", "Top topic", "Relevance", "HTTP", "Freshness", "Live"],
                              prov_rows, styles, [58.0, 44.0, 22.0, 16.0, 22.0, 8.0]))
    else:
        el.append(_empty_note(styles, "provenance rows"))

    el.append(Paragraph("14.6 Deliverables shipped with this job", styles["h3"]))
    el.append(Paragraph(
        "dashboard.html (interactive) · report.json (raw evidence) · proximity_scores.csv · "
        "entity_citation_summary.csv · off_page_targets.csv · recommendations.csv · "
        "share_of_voice_heatmap.csv · token_density_adjuster.csv · sentiment_audit.csv · "
        "poisoning_sources.csv · semantic_drift.csv · synthetic_retrieval_queries.csv · "
        "rag_content_brief.md · schema_jsonld_patch.json · this PDF. Re-run or schedule "
        "weekly — deltas land in History &amp; Trends with per-topic drift alerts.",
        styles["body"]))

    # ================= APPENDIX ==============================================================
    el.append(_section_band("A", "Appendix · Thresholds &amp; Methods Glossary", styles))
    thresh = meta.get("topic_thresholds", {}) or {}
    if thresh:
        el.append(Paragraph("Auto-calibrated per-topic relevance thresholds", styles["h3"]))
        el.append(_grid_table(["Topic", "Threshold"],
                              [[k, _r(v)] for k, v in sorted(thresh.items())[:30]],
                              styles, [120.0, 50.0]))
    el.append(Paragraph("Methods glossary (one line each)", styles["h3"]))
    el.append(_kv_table([
        ["Cosine proximity", "Angle between brand/entity and topic vectors; 0 unrelated, 1 identical."],
        ["RAG Invisibility Index", "Share of high-relevance passages omitting the brand while citing rivals."],
        ["Vector share of voice", "Brand retrieval weight across topic × entity comparisons."],
        ["Chunk windows", "512-token (default) retrieval windows with 64-token overlap."],
        ["Drift delta", "Current run metric minus prior run metric from the time-series DB."],
        ["Net sentiment", "Positive-window share minus negative-window share per entity."],
        ["Synthetic query", "Reverse-engineered prompt that retrieves a given chunk."],
        ["Token density", "On-window brand token share; 1.5% default displacement goal."],
        ["Machine score", "Heuristic spam signal: repetition + template phrases + link density."],
        ["Freshness grade", "0.6 × live + 0.3 × current + 0.1 × age-known, from real HTTP dates."],
    ], styles))

    el.append(Spacer(1, 8))
    el.append(HRFlowable(width="100%", color=LINE))
    el.append(Paragraph(
        "Generated locally by ragevda. Figures reproduce from the job's report.json. "
        "Decision-support artifact — not a certification of third-party content accuracy.",
        styles["small"]))

    doc.build(el)
    return out_path


def drift_rows_sort(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order drift ledger by relevance so the most-watched topics print first."""
    try:
        return sorted(items, key=lambda r: int(r.get("relevant_docs") or 0), reverse=True)
    except (TypeError, ValueError):
        return items


def branch_neg(row: Dict[str, Any]) -> float:
    """Negative share for the brand framing pie (defensive float)."""
    try:
        return float(row.get("negative_pct") or 0)
    except (TypeError, ValueError):
        return 0.0


def short_engine(name: Any) -> str:
    """Compact AI-surface labels so chart axes stay legible."""
    s = str(name or "")
    mapping = {
        "Google AI Overviews": "AI Overviews",
        "Bing Copilot": "Copilot",
        "Google News": "G News",
    }
    return mapping.get(s, s[:16])
