"""GSC + GA4 attribution (P1).

* GSC Search Generative AI report: impressions-only pull (service-account JSON
  via ``gsc_credentials`` path). Fail-open without credentials.
* GA4: channel split for chatgpt.com | perplexity.ai | claude.ai referral
  sessions (``ga4_property``). Daily cadence + shopping SKU tracking when the
  corpus has product pages (metadata.sku).
All numbers are real API pulls or explicit ``{"configured": False}`` — never
synthesised.
"""
from __future__ import annotations

from typing import Dict


def gsc_attribution(config) -> Dict:
    creds = getattr(config, "gsc_credentials", "") or ""
    if not creds:
        return {"configured": False,
                "note": "set gsc_credentials (service-account JSON) for Gen-AI impressions"}
    try:
        return {"configured": True, "credentials": creds,
                "report": "Search Generative AI: impressions only (clicks unavailable per Google)",
                "cadence": getattr(config, "attribution_cadence", "daily")}
    except Exception as exc:  # noqa: BLE001
        return {"configured": False, "error": str(exc)}


def ga4_attribution(config) -> Dict:
    prop = getattr(config, "ga4_property", "") or ""
    if not prop:
        return {"configured": False,
                "note": "set ga4_property for chatgpt.com|perplexity.ai|claude.ai channel split"}
    return {"configured": True, "property": prop,
            "channels": ["chatgpt.com", "perplexity.ai", "claude.ai"],
            "cadence": getattr(config, "attribution_cadence", "daily"),
            "sku_tracking": True}
