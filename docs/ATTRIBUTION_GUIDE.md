# Attribution wiring — GSC Gen-AI + GA4 LLM referrals (end to end)

Stubs that lie are worse than no stubs. Ours are wired + explicit
`{"configured": false}` without creds — never synthesised.
(`ragevda/attribution.py`, surfaced in dashboard + `report.json`.)

1. **GSC Search Generative AI report** (UK Jun 3 2026, worldwide Aug 31 2026):
   set `gsc_credentials` to a service-account JSON with
   `webmasters.readonly`. Pull = impressions only (clicks unavailable per
   Google) by page/country/device. AI Mode queries come from the **regular**
   Performance report (the AI report has no query dimension).
2. **GA4 Data API LLM-referral split**: set `ga4_property`; channels split
   chatgpt / perplexity / gemini / claude. Pair with the GSC pull — GSC says
   what AI *showed*, GA4 says what AI *sent*.
3. **Slack drift alerts**: set `drift_webhook_url` (or `SLACK_WEBHOOK_URL`);
   `tracking.drift_alert()` fires at ±5 pp composite SoV. ETS-lite forecast
   lives in `advanced.drift.forecast`.

Agency tip: screenshot the wired GSC table once (blur client IDs) — that one
image outsells ten "coming soon" badges. Until then the dashboard shows the
honest "not configured" card with setup steps.
