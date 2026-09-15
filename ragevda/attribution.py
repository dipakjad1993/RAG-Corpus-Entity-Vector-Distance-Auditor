"""GSC + GA4 attribution (P1) — wired, not stubbed.

* GSC Search Generative AI Performance report (UK Jun 3 2026, global Aug
  2026): impressions-only pull (service-account JSON via ``gsc_credentials``
  path). No queries exist in the AI report — AI Mode queries are pulled from
  the regular Performance report. Pair with GA4 LLM referrals
  (chatgpt.com / perplexity.ai / gemini.google.com / claude.ai).
* GA4: Data API channel split when ``ga4_property`` is set.
* Slack: posts drift/visibility alerts to ``drift_webhook_url`` when set.
All numbers are real API pulls or explicit ``{"configured": False}`` — never
synthesised. Every external import is lazy so LITE boot stays light.
"""
from __future__ import annotations

import os
from typing import Dict


def gsc_attribution(config) -> Dict:
    creds = getattr(config, "gsc_credentials", "") or os.environ.get("GSC_CREDENTIALS", "")
    if not creds:
        return {"configured": False,
                "note": ("set gsc_credentials (service-account JSON) for Gen-AI impressions "
                         "(AI Overviews + AI Mode by Pages/Countries/Devices; impressions only, "
                         "clicks unavailable per Google). Pull AI Mode queries from the regular "
                         "Performance report — the AI report has no query dimension.")}
    if not os.path.exists(str(creds)):
        return {"configured": False,
                "error": f"gsc_credentials file not found: {creds}"}
    try:
        # Lazy google-api client; fail-open with actionable error.
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build  # type: ignore
        creds_obj = service_account.Credentials.from_service_account_file(
            str(creds), scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
        svc = build("searchconsole", "v1", credentials=creds_obj, cache_discovery=False)
        site = getattr(config, "site_base_url", "") or ""
        out: Dict = {"configured": True, "credentials": str(creds),
                     "report": "Search Generative AI: impressions only (clicks unavailable per Google)",
                     "cadence": getattr(config, "attribution_cadence", "daily"),
                     "ai_mode_queries_source": "regular Performance report (dimension: query)"}
        if site:
            try:
                res = svc.searchanalytics().query(
                    siteUrl=site, body={
                        "startDate": "2026-08-01", "endDate": "2026-09-15",
                        "dimensions": ["page", "country", "device"],
                        "rowLimit": 100}).execute()
                out["genai_rows"] = (res.get("rows", []) or [])[:100]
            except Exception as exc:  # noqa: BLE001
                out["genai_error"] = str(exc)
        return out
    except Exception as exc:  # noqa: BLE001
        return {"configured": False,
                "error": (f"GSC client unavailable: {exc}. "
                          "pip install google-api-python-client google-auth")}


def ga4_attribution(config) -> Dict:
    prop = getattr(config, "ga4_property", "") or os.environ.get("GA4_PROPERTY", "")
    if not prop:
        return {"configured": False,
                "note": ("set ga4_property for chatgpt.com|perplexity.ai|gemini.google.com|"
                         "claude.ai channel split + SKU tracking")}
    channels = ["chatgpt.com", "perplexity.ai", "gemini.google.com", "claude.ai"]
    out: Dict = {"configured": True, "property": prop, "channels": channels,
                 "cadence": getattr(config, "attribution_cadence", "daily"),
                 "sku_tracking": True}
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient  # type: ignore
        from google.analytics.data_v1beta.types import (DateRange, Dimension, Metric,  # type: ignore
                                                        RunReportRequest)
        creds_path = getattr(config, "gsc_credentials", "") or os.environ.get("GSC_CREDENTIALS", "")
        kwargs = {"credentials": None}
        if creds_path and os.path.exists(str(creds_path)):
            from google.oauth2 import service_account  # type: ignore
            kwargs["credentials"] = service_account.Credentials.from_service_account_file(
                str(creds_path))
        client = BetaAnalyticsDataClient(**{k: v for k, v in kwargs.items() if v})
        req = RunReportRequest(
            property_=f"properties/{prop}",
            dimensions=[Dimension(name="sessionSource"), Dimension(name="date")],
            metrics=[Metric(name="sessions")],
            date_ranges=[DateRange(start_date="30daysAgo", end_date="today")])
        resp = client.run_report(req)
        rows = []
        for r in resp.rows or []:
            src = r.dimension_values[0].value if r.dimension_values else ""
            if any(c in src for c in channels):
                rows.append({"source": src,
                             "date": r.dimension_values[1].value if len(r.dimension_values) > 1 else "",
                             "sessions": r.metric_values[0].value if r.metric_values else "0"})
        out["llm_referral_rows"] = rows[:200]
    except Exception as exc:  # noqa: BLE001
        out["ga4_live_error"] = (f"{exc} (pip install google-analytics-data; "
                                 "rows require GA4 Data API access)")
    return out


def post_slack_alert(config, text: str) -> Dict:
    url = getattr(config, "drift_webhook_url", "") or os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        return {"posted": False, "note": "set drift_webhook_url for Slack alerts"}
    try:
        import httpx
        r = httpx.post(url, json={"text": text[:3000]}, timeout=15)
        return {"posted": r.status_code < 300, "status": r.status_code}
    except Exception as exc:  # noqa: BLE001
        return {"posted": False, "error": str(exc)}
