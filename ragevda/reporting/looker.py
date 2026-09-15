"""Looker Studio connector bundle (enterprise plumbing).

Generates ``looker_connector.json`` — a declarative schema + row dump the
Looker Studio community-connector starter can ingest — plus a lean
``looker_rows.csv`` (no pandas required; stdlib csv only so Render LITE
stays light). Real report numbers only.
"""
from __future__ import annotations

import csv
import json
import os
from typing import Dict


def write_looker_bundle(out_dir: str, report: Dict, config) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    vis = (report.get("advanced", {}) or {}).get("visibility", {}) or {}
    rows = []
    for r in vis.get("table", []) or []:
        rows.append({"entity": r.get("entity", ""),
                     "visibility": r.get("visibility", 0),
                     "position": r.get("position", 0),
                     "mentions": r.get("mentions", 0),
                     "citations_linked": r.get("citations_linked", 0)})
    for t in (report.get("invisibility", {}) or {}).get("per_topic", []) or []:
        rows.append({"entity": "__topic__", "topic": t.get("topic", ""),
                     "visibility": t.get("vector_share_of_voice_pct", 0)})
    schema = [{"name": "entity", "type": "string"},
              {"name": "topic", "type": "string"},
              {"name": "visibility", "type": "number"},
              {"name": "position", "type": "number"},
              {"name": "mentions", "type": "number"},
              {"name": "citations_linked", "type": "number"}]
    p1 = os.path.join(out_dir, "looker_connector.json")
    with open(p1, "w", encoding="utf-8") as fh:
        json.dump({"connector": "ragevda-looker-studio", "brand": config.target_brand,
                   "schema": schema, "rows": rows[:500]}, fh, indent=2)
    p2 = os.path.join(out_dir, "looker_rows.csv")
    with open(p2, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["entity", "topic", "visibility",
                                           "position", "mentions", "citations_linked"])
        w.writeheader()
        for r in rows[:500]:
            w.writerow({"entity": r.get("entity", ""), "topic": r.get("topic", ""),
                        "visibility": r.get("visibility", 0),
                        "position": r.get("position", 0),
                        "mentions": r.get("mentions", 0),
                        "citations_linked": r.get("citations_linked", 0)})
    return {"looker_connector.json": p1, "looker_rows.csv": p2}
