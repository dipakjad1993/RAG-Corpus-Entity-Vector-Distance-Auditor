"""TL;DR Executive Verdict card (P0 packaging).

The #1 screenshot on LinkedIn: one card with Visibility 0-100, Position,
Mentions vs linked-Citations split, delta vs competitor median, plus the
single sentence a CMO reads. All inputs are REAL report evidence
(visibility table, invisibility composite, E-E-A-T gate, drift alerts).

Stdlib only.
"""
from __future__ import annotations

from typing import Dict


def compute_exec_verdict(report: Dict, brand: str = "") -> Dict:
    adv = (report or {}).get("advanced", {}) or {}
    vis = adv.get("visibility", {}) or {}
    inv = (report or {}).get("invisibility", {}) or {}
    table = vis.get("table", []) or []
    brand_row = next((r for r in table if r.get("entity") == brand), None)
    if brand_row is None and table:
        brand_row = next((r for r in table
                          if str(r.get("entity", "")).lower() == str(brand or "").lower()), None)

    visibility = float((brand_row or {}).get("visibility", 0.0) or 0.0)
    position = (brand_row or {}).get("position")
    mentions = int((brand_row or {}).get("mentions", 0) or 0)
    linked = int((brand_row or {}).get("citations_linked", 0) or 0)
    delta = float(vis.get("delta_vs_median", 0.0) or 0.0)
    invis = float(inv.get("composite_invisibility_index_pct", 0.0) or 0.0)
    sov = float(inv.get("composite_vector_share_of_voice_pct", 0.0) or 0.0)

    eeat = adv.get("eeat", {}) or {}
    eeat_avg = eeat.get("avg_score")
    drift_alerts = ((adv.get("drift", {}) or {}).get("alerts", []) or [])

    # Verdict ladder (auditable thresholds, documented in docs/EXEC_VERDICT.md).
    if visibility >= 60 and invis <= 25 and delta >= 0:
        verdict, tone = "WINNING — defend the lead", "good"
    elif visibility >= 40 and invis <= 50:
        verdict, tone = "COMPETITIVE — close the top-2 gaps", "warn"
    elif (isinstance(eeat_avg, (int, float)) and eeat_avg < 50) or invis >= 70:
        verdict, tone = "CRITICAL — invisible or untrusted where it matters", "critical"
    else:
        verdict, tone = "AT RISK — targeted outreach required", "warn"

    if delta >= 5:
        sentence = (f"{brand or 'Brand'} leads the competitor median by +{delta:.1f} "
                    f"visibility points at {visibility:.1f} (#{position or '–'}), "
                    f"but is still absent from {invis:.0f}% of high-relevance articles.")
    elif delta <= -5:
        sentence = (f"{brand or 'Brand'} trails the competitor median by {delta:.1f} "
                    f"points at {visibility:.1f} (#{position or '–'}) with "
                    f"{invis:.0f}% invisibility — the pitch list below is the recovery plan.")
    else:
        sentence = (f"{brand or 'Brand'} sits at {visibility:.1f} visibility "
                    f"(#{position or '–'}, {invis:.0f}% invisible, SoV {sov:.0f}%) — "
                    f"neck-and-neck with the median competitor.")

    return {
        "brand": brand,
        "visibility": round(visibility, 1),
        "position": position,
        "mentions": mentions,
        "citations_linked": linked,
        "citations_unlinked": max(0, mentions - linked),
        "delta_vs_median": round(delta, 1),
        "invisibility_pct": round(invis, 1),
        "sov_pct": round(sov, 1),
        "eeat_avg": eeat_avg,
        "drift_alert_count": len(drift_alerts),
        "verdict": verdict,
        "tone": tone,
        "sentence": sentence,
        "method": ("visibility=100*(0.7*mean_proximity+0.3*mention_share); "
                   "position=rank; delta=brand-competitor_median; "
                   "invisibility=% high-relevance docs without brand"),
    }
