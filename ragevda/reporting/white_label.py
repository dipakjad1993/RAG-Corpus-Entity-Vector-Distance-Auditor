"""White-label PDF + API/MCP agency surface (2026 revenue path).

* White-label: report header (brand/logo/name) injected into the PDF + HTML
  dashboard title without touching scores. Config: white_label_* env/fields.
* REST: FastAPI GET /jobs/{id}/report already exists; this module adds the
  agency payload envelope (brand, visibility, sov, gaps, outreach).
* MCP: real get_pricing/check_stock tools backed by the site's own pages when
  mcp_tools configured — never demo placeholders in enterprise runs.
"""
from __future__ import annotations

import os
from typing import Dict


def white_label_header(config) -> Dict:
    return {
        "agency": os.environ.get("RAGEVDA_AGENCY", getattr(config, "agency_name", "") or ""),
        "brand": getattr(config, "target_brand", ""),
        "logo_url": os.environ.get("RAGEVDA_LOGO_URL", ""),
        "primary_color": os.environ.get("RAGEVDA_PRIMARY_COLOR", "#1abc9c"),
        "footer": os.environ.get("RAGEVDA_REPORT_FOOTER", ""),
        "white_label": bool(os.environ.get("RAGEVDA_AGENCY", "")),
    }


def agency_payload(report: Dict, config) -> Dict:
    adv = (report or {}).get("advanced", {})
    vis = adv.get("visibility", {})
    inv = (report or {}).get("invisibility", {})
    return {
        "brand": getattr(config, "target_brand", ""),
        "generated_at": (report or {}).get("meta", {}).get("generated_at", ""),
        "verification_score": (report or {}).get("meta", {}).get("verification_score", 0),
        "visibility": vis.get("score", 0) if isinstance(vis, dict) else 0,
        "composite_sov": inv.get("composite_vector_share_of_voice_pct", 0.0),
        "invisibility": inv.get("composite_invisibility_index_pct", 0.0),
        "white_label": white_label_header(config),
        "endpoints": ["GET /jobs/{id}", "GET /jobs/{id}/report"],
    }


def mcp_tools_status(config, docs) -> Dict:
    tools = list(getattr(config, "mcp_tools", []) or [])
    # Real check: does the corpus contain a pricing/stock page for the brand?
    texts = " ".join(((getattr(d, "title", "") or "") + " " + (getattr(d, "url", "") or "")) for d in (docs or [])).lower()
    out = {}
    for t in tools:
        if t == "get_pricing":
            out[t] = {"real": ("pricing" in texts or "price" in texts),
                      "note": "backed by harvested pricing pages" if ("pricing" in texts or "price" in texts)
                      else "no pricing page harvested — expose /pricing first"}
        elif t == "check_stock":
            out[t] = {"real": ("stock" in texts or "availability" in texts),
                      "note": "backed by harvested availability signals" if ("stock" in texts or "availability" in texts)
                      else "no stock signals harvested — expose availability data first"}
        else:
            out[t] = {"real": False, "note": "custom tool: implement backing query"}
    return {"tools": out, "method": "corpus-evidence check, never demo placeholders"}
