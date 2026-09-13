"""Consolidated report writer — the 5-output contract (2026).

Replaces the 22-file sprawl: every audit emits EXACTLY
  report.json (machine) + dashboard.html (human) + corpus.duckdb +
  drift_timeseries.duckdb (analyst) + rag_content_brief.md + llms.txt patch
  (action). Legacy CSVs/brief/patch writers remain as shims (archived/).
"""
from __future__ import annotations

import os
from typing import Dict

from .csv_json import write_json, write_csvs
from .dashboard import write_dashboard
from .brief import write_rag_brief, write_jsonld
from .llms import write_llms_outputs

CORE = ["report.json", "dashboard.html", "corpus.duckdb",
        "drift_timeseries.duckdb", "rag_content_brief.md",
        "llms.txt", "agent.json", ".well-known/mcp.json"]


def write_consolidated(out_dir: str, report: Dict, config,
                       archive_legacy_csvs: bool = True) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    paths: Dict[str, str] = {}
    jp = os.path.join(out_dir, "report.json")
    write_json(jp, report)
    paths["report.json"] = jp
    hp = os.path.join(out_dir, "dashboard.html")
    write_dashboard(hp, report)
    paths["dashboard.html"] = hp
    bp = os.path.join(out_dir, "rag_content_brief.md")
    write_rag_brief(bp, report)
    paths["brief"] = bp
    sp = os.path.join(out_dir, "schema_jsonld_patch.json")
    write_jsonld(sp, report)
    paths["jsonld"] = sp
    paths.update(write_llms_outputs(out_dir, report, config))
    if archive_legacy_csvs:
        legacy = os.path.join(out_dir, "_legacy")
        os.makedirs(legacy, exist_ok=True)
        for p in write_csvs(legacy, report):
            paths.setdefault("legacy_csv", p)
    return paths
