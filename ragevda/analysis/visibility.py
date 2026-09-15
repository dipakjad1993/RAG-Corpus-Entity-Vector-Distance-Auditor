"""C-suite Visibility Score (Semrush-style, auditable).

Translates 0-1 cosine proximity + invisibility % into executive metrics:

* **Visibility 0-100** per entity: 100 * weighted mean proximity mass,
  blended with retrieval share (top-k hits) — never a black box; every
  component exported.
* **Position**: rank of entity by visibility (1 = leader).
* **Mentions vs Citations split**: raw mention count vs linked-citation
  count (from citation_gap ledger).
* **Competitor median delta**: brand visibility minus median competitor
  visibility (positive = beating the median, like Semrush AI Visibility
  Score vs median).

All inputs are REAL report evidence (proximity rows, citation ledger).
No synthesis.
"""
from __future__ import annotations

import statistics
from typing import Dict, List


def compute_visibility(report: Dict, config) -> Dict:
    prox_rows: List[Dict] = (report.get("proximity", {}) or {}).get("rows", []) or []
    cit = report.get("citation_gap", {}) or {}
    citations: List[Dict] = cit.get("citations", []) or []

    brand = config.target_brand
    entities = [brand] + list(config.competitor_entities or [])

    # per-entity mean proximity across topics
    prox_by_ent: Dict[str, List[float]] = {e: [] for e in entities}
    for r in prox_rows:
        e = r.get("entity", "")
        if e in prox_by_ent:
            try:
                prox_by_ent[e].append(float(r.get("proximity", 0) or 0))
            except (TypeError, ValueError):
                pass

    # mentions vs citations
    mentions = {e: 0 for e in entities}
    for r in prox_rows:
        e = r.get("entity", "")
        if e in mentions:
            try:
                mentions[e] += int(r.get("mentions", 0) or 0)
            except (TypeError, ValueError):
                pass
    linked = {e: 0 for e in entities}
    for c in citations:
        e = c.get("entity", "")
        if e in linked and str(c.get("status", "")).lower() in ("linked", "cited", "citation"):
            try:
                linked[e] += int(c.get("count", 1) or 1)
            except (TypeError, ValueError):
                linked[e] += 1

    # visibility = 100 * (0.7*mean_prox + 0.3*mention_share)
    total_mentions = sum(mentions.values()) or 1
    table = []
    for e in entities:
        mean_prox = (sum(prox_by_ent[e]) / len(prox_by_ent[e])) if prox_by_ent[e] else 0.0
        share = mentions[e] / total_mentions
        visibility = round(100.0 * (0.7 * mean_prox + 0.3 * min(1.0, share * len(entities))), 1)
        table.append({
            "entity": e,
            "visibility": visibility,
            "mean_proximity": round(mean_prox, 4),
            "mentions": mentions[e],
            "citations_linked": linked[e],
            "citations_unlinked": max(0, mentions[e] - linked[e]),
            "mention_share_pct": round(100.0 * share, 1),
        })
    table.sort(key=lambda r: r["visibility"], reverse=True)
    for i, r in enumerate(table):
        r["position"] = i + 1
    comp_vis = [r["visibility"] for r in table if r["entity"] != brand]
    median_comp = round(statistics.median(comp_vis), 1) if comp_vis else 0.0
    brand_row = next((r for r in table if r["entity"] == brand), None)
    delta = round((brand_row["visibility"] - median_comp), 1) if brand_row else 0.0
    return {
        "table": table,
        "brand_visibility": brand_row["visibility"] if brand_row else 0.0,
        "brand_position": brand_row["position"] if brand_row else None,
        "competitor_median_visibility": median_comp,
        "delta_vs_median": delta,
        "method": ("visibility=100*(0.7*mean_proximity+0.3*mention_share); "
                   "position=rank; citations_linked from citation ledger; "
                   "delta=brand-competitor_median (Semrush-style)"),
    }
