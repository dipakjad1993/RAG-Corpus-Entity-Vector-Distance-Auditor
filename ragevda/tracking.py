"""Run history, trend tracking and diff engine.

Every completed audit writes ``report.json`` into ``web_output/jobs/<jobid>/``.
This module discovers those runs, extracts a comparable metric set, and builds:

* a **trend series** (composite Vector Share-of-Voice and RAG Invisibility Index
  over time, per brand), and
* a **diff** between any two runs (per-topic invisibility / SoV deltas) so a user
  can see exactly what improved or regressed after an outreach campaign.

All charts are rendered as self-contained inline SVG (no JS/CDN) so the history
page stays fully offline like the rest of the tool.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .utils import get_logger

logger = get_logger("ragevda.tracking")

DEFAULT_JOBS_DIR = os.path.join("web_output", "jobs")


@dataclass
class RunRecord:
    job_id: str
    generated_at: datetime
    brand: str
    topics: List[str]
    competitors: List[str]
    doc_count: int
    rag_invisibility_index: float
    composite_sov: float
    per_topic: Dict[str, Dict[str, float]] = field(default_factory=dict)
    config_key: str = ""

    @property
    def label(self) -> str:
        return f"{self.brand} @ {self.generated_at.strftime('%Y-%m-%d %H:%M')}"


def _parse_ts(s: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def load_runs(jobs_dir: str = DEFAULT_JOBS_DIR) -> List[RunRecord]:
    """Scan the jobs directory and return all valid runs, newest last."""
    if not os.path.isdir(jobs_dir):
        return []
    runs: List[RunRecord] = []
    for entry in sorted(os.listdir(jobs_dir)):
        rj = os.path.join(jobs_dir, entry, "report.json")
        if not os.path.isfile(rj):
            continue
        try:
            with open(rj, "r", encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            logger.warning("skip unreadable run %s: %s", entry, exc)
            continue
        try:
            meta = d["meta"]
            cfg = meta["config"]
            inv = d.get("invisibility", {})
            per_topic = {}
            for t in inv.get("per_topic", []):
                per_topic[t["topic"]] = {
                    "invisibility": t.get("topic_invisibility_pct", 0.0),
                    "sov": t.get("vector_share_of_voice_pct", 0.0),
                    "relevant_docs": t.get("relevant_docs", 0),
                }
            topics = cfg.get("industry_topics", []) or []
            comps = cfg.get("competitor_entities", []) or []
            key = (cfg.get("target_brand", "") + "|" + "|".join(sorted(topics))
                   + "||" + "|".join(sorted(comps)))
            ts = _parse_ts(meta.get("generated_at", "") or "")
            if ts is None:
                # Corrupt timestamp: fall back to the report file mtime so the
                # run sorts by real filesystem recency instead of datetime.min
                # (which would wrongly sort first and fake the trend origin).
                try:
                    ts = datetime.fromtimestamp(os.path.getmtime(rj))
                except OSError:
                    logger.warning("skip run with unparseable timestamp %s", entry)
                    continue
            runs.append(RunRecord(
                job_id=entry,
                generated_at=ts,
                brand=cfg.get("target_brand", ""),
                topics=topics,
                competitors=comps,
                doc_count=meta.get("context_stats", {}).get("doc_count", 0),
                rag_invisibility_index=inv.get("composite_invisibility_index_pct", 0.0),
                composite_sov=inv.get("composite_vector_share_of_voice_pct", 0.0),
                per_topic=per_topic,
                config_key=key,
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("skip malformed run %s: %s", entry, exc)
            continue
    runs.sort(key=lambda r: r.generated_at)
    return runs


def brands(runs: List[RunRecord]) -> List[str]:
    seen, out = set(), []
    for r in runs:
        if r.brand and r.brand not in seen:
            seen.add(r.brand)
            out.append(r.brand)
    return out


def runs_for_brand(runs: List[RunRecord], brand: str) -> List[RunRecord]:
    return [r for r in runs if r.brand == brand]


def diff_runs(new: RunRecord, old: RunRecord) -> List[Dict]:
    """Per-topic deltas between two runs (new vs old)."""
    rows = []
    all_topics = list(dict.fromkeys(list(new.per_topic.keys()) + list(old.per_topic.keys())))
    for topic in all_topics:
        n = new.per_topic.get(topic, {})
        o = old.per_topic.get(topic, {})
        inv_n, inv_o = n.get("invisibility", 0.0), o.get("invisibility", 0.0)
        sov_n, sov_o = n.get("sov", 0.0), o.get("sov", 0.0)
        rows.append({
            "topic": topic,
            "inv_old": inv_o, "inv_new": inv_n, "inv_delta": round(inv_n - inv_o, 2),
            "sov_old": sov_o, "sov_new": sov_n, "sov_delta": round(sov_n - sov_o, 2),
            "relevant_new": n.get("relevant_docs", 0),
            "improved": (inv_n - inv_o) < -0.5 or (sov_n - sov_o) > 0.5,
            "worsened": (inv_n - inv_o) > 0.5 or (sov_n - sov_o) < -0.5,
        })
    rows.sort(key=lambda x: abs(x["inv_delta"]) + abs(x["sov_delta"]), reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Offline SVG charts
# ---------------------------------------------------------------------------
def _svg_line_chart(series: List[Tuple[str, List[float], str]], width: int = 720,
                    height: int = 260, y_max: float = 100.0,
                    y_label: str = "%") -> str:
    """series = [(legend, values, color), ...]; x = run index."""
    n = max((len(v[1]) for v in series), default=0)
    if n == 0:
        return "<p class='muted'>No data points yet.</p>"
    pad_l, pad_r, pad_t, pad_b = 44, 16, 16, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    parts = [f"<svg viewBox='0 0 {width} {height}' width='100%' "
             f"xmlns='http://www.w3.org/2000/svg' role='img'>"]
    for g in range(0, 6):
        yv = y_max * g / 5.0
        y = pad_t + plot_h - (yv / y_max) * plot_h
        parts.append(f"<line x1='{pad_l}' y1='{y:.1f}' x2='{width-pad_r}' y2='{y:.1f}' "
                     f"stroke='#2a3354' stroke-width='1'/>")
        parts.append(f"<text x='{pad_l-6}' y='{y+3:.1f}' fill='#9aa6c4' "
                     f"font-size='10' text-anchor='end'>{yv:.0f}{y_label}</text>")
    parts.append(f"<line x1='{pad_l}' y1='{pad_t}' x2='{pad_l}' y2='{pad_t+plot_h}' "
                 f"stroke='#46527a'/>")
    parts.append(f"<line x1='{pad_l}' y1='{pad_t+plot_h}' x2='{width-pad_r}' "
                 f"y2='{pad_t+plot_h}' stroke='#46527a'/>")
    for idx, (legend, vals, color) in enumerate(series):
        if len(vals) < 1:
            continue
        pts = []
        for i, v in enumerate(vals):
            x = pad_l + (plot_w * i / max(1, n - 1)) if n > 1 else pad_l + plot_w / 2
            y = pad_t + plot_h - (min(v, y_max) / y_max) * plot_h
            pts.append(f"{x:.1f},{y:.1f}")
        parts.append(f"<polyline points='{' '.join(pts)}' fill='none' "
                     f"stroke='{color}' stroke-width='2.5' "
                     f"stroke-linejoin='round' stroke-linecap='round'/>")
        for i, v in enumerate(vals):
            x = pad_l + (plot_w * i / max(1, n - 1)) if n > 1 else pad_l + plot_w / 2
            y = pad_t + plot_h - (min(v, y_max) / y_max) * plot_h
            parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3' fill='{color}'/>")
        lx = pad_l + 8
        ly = pad_t + 12 + idx * 14
        parts.append(f"<rect x='{lx}' y='{ly-8}' width='10' height='10' fill='{color}'/>")
        parts.append(f"<text x='{lx+14}' y='{ly+1}' fill='#c7d0e6' font-size='11'>{legend}</text>")
    parts.append("</svg>")
    return "".join(parts)


def trend_chart(runs: List[RunRecord], metric: str = "both") -> str:
    """metric: 'sov' | 'invisibility' | 'both'."""
    if not runs:
        return "<p class='muted'>No runs recorded yet for this brand.</p>"
    labels = [r.generated_at.strftime("%m-%d %H:%M") for r in runs]
    sov = [r.composite_sov for r in runs]
    inv = [r.rag_invisibility_index for r in runs]
    series = []
    if metric in ("sov", "both"):
        series.append(("Vector Share of Voice %", sov, "#1abc9c"))
    if metric in ("invisibility", "both"):
        series.append(("RAG Invisibility Index %", inv, "#e67e22"))
    svg = _svg_line_chart(series, y_max=100.0)
    xticks = "".join(
        f"<span style='flex:1;text-align:center;color:#9aa6c4;font-size:10px'>{l}</span>"
        for l in labels
    )
    return svg + f"<div style='display:flex;margin-left:44px'>{xticks}</div>"


def per_topic_trend_chart(runs: List[RunRecord], topic: str) -> str:
    if not runs:
        return "<p class='muted'>No runs.</p>"
    sov = [r.per_topic.get(topic, {}).get("sov", 0.0) for r in runs]
    inv = [r.per_topic.get(topic, {}).get("invisibility", 0.0) for r in runs]
    labels = [r.generated_at.strftime("%m-%d %H:%M") for r in runs]
    series = [("SoV %", sov, "#1abc9c"), ("Invisibility %", inv, "#e67e22")]
    svg = _svg_line_chart(series, y_max=100.0)
    xticks = "".join(
        f"<span style='flex:1;text-align:center;color:#9aa6c4;font-size:10px'>{l}</span>"
        for l in labels
    )
    return svg + f"<div style='display:flex;margin-left:44px'>{xticks}</div>"
