"""Deep-analysis section split (god-file refactor part 2/2).

reporting/deep_analysis.py (1373L) now delegates P0 GEO sections here.
Each builder takes (report, config) and returns markdown — pure functions,
unit-testable, no I/O. deep_analysis.py imports these (facade preserved).
"""
from __future__ import annotations

from typing import Dict


def md_citation_steals(report: Dict) -> str:
    steals = ((report.get("advanced", {}) or {}).get("citation_reverse", {}) or {}).get("steals", [])
    if not steals:
        return "## Citation steals\n\nNo steal-worthy passages (cosine < 0.88) in this corpus.\n"
    lines = ["## Citation steals (passage-BERT, verbatim)"]
    for s in steals[:10]:
        lines.append(f"\n### {s.get('doc_title', '')[:80]} ({s.get('cosine', 0)})")
        lines.append(f"URL: {s.get('doc_url', '')}\nVerdict: **{s.get('verdict', '')}**")
        lines.append(f"> {s.get('passage', '')[:400]}")
        lines.append(f"Action: {s.get('action', '')}")
    return "\n".join(lines) + "\n"


def md_fanout(report: Dict) -> str:
    cov = ((report.get("advanced", {}) or {}).get("fanout_coverage", {}) or {})
    if not cov.get("clusters"):
        return "## Fan-out coverage\n\nNo fan-out data.\n"
    lines = [f"## Fan-out coverage (avg {cov.get('avg_coverage_pct', 0)}%)"]
    for c in cov["clusters"][:10]:
        uncovered = [s["fanout"] for s in c.get("slices", []) if not s.get("covered")][:5]
        lines.append(f"\n### {c.get('prompt', '')[:80]} — {c.get('coverage_pct', 0)}%")
        for u in uncovered:
            lines.append(f"- GAP: {u}")
    return "\n".join(lines) + "\n"


def md_eeat_gain(report: Dict) -> str:
    adv = report.get("advanced", {}) or {}
    eeat = adv.get("eeat", {}) or {}
    gain = adv.get("entity_gain", {}) or {}
    lines = ["## E-E-A-T gate + Entity density",
             f"\nE-E-A-T avg {eeat.get('avg_score', 0)} | critical {eeat.get('critical_count', 0)} | "
             f"pass rate {eeat.get('pass_rate_pct', 0)}%",
             f"Entity-gain avg {gain.get('avg_score', 0)} (target 15+ entities/page)."]
    for r in (gain.get("rows", []) or [])[:5]:
        lines.append(f"\n- {r.get('title', '')[:70]}: score {r.get('score', 0)}")
        for f in (r.get("fixes", []) or [])[:2]:
            lines.append(f"  - fix: {f}")
    return "\n".join(lines) + "\n"


def md_media_multilingual(report: Dict) -> str:
    adv = report.get("advanced", {}) or {}
    media = adv.get("media", {}) or {}
    ml = adv.get("multilingual", {}) or {}
    s = (media.get("summary", {}) or {})
    lines = ["## Media + Multilingual",
             f"\nImages {s.get('image_pct', 0)}% | video {s.get('video_pct', 0)}% | "
             f"offer {s.get('offer_pct', 0)}% | GBP {s.get('gbp_pct', 0)}%",
             f"Languages: {ml.get('lang_counts', {})} | geo: {ml.get('geo_variants', [])}"]
    for rec in (media.get("recommendations", []) or []):
        lines.append(f"- {rec}")
    for g in (ml.get("gaps", []) or []):
        lines.append(f"- {g}")
    return "\n".join(lines) + "\n"
