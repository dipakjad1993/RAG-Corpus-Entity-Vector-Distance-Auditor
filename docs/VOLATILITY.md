# Volatility & citation decay — why single-sample scores lie

LLM answers vary run to run (temperature + retrieval noise). A vendor score
from one sample is marketing, not measurement.

RAG-EVDA reports volatility honestly:

* `answer_repeats: 5-10` (with `answer_harvester: multi` + Brave/Tavily/Exa
  keys) samples each prompt Nx -> per-prompt **mean ± stdev**.
* Status ladder: **STABLE** (stdev < 0.08) / **WATCH** (< 0.15) / **VOLATILE**
  (>= 0.15). Single-sample runs are labelled **SINGLE_SAMPLE** / **UNKNOWN** —
  never smoothed.
* `advanced.volatility.citation_decay` ranks topics by week-over-week Δ SoV /
  Δ proximity from `drift_timeseries.duckdb` (same source as drift alerts).

Dashboard: "Answer Volatility & Citation Decay" section + `decay_alerts()`
fires at ±5 pp SoV (Slack via `drift_webhook_url`).

Cost honesty: repeats multiply paid-API calls. Triage without keys = n=1,
labelled as such. That is the point — honest beats pretty.
