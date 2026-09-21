# Serving — FastAPI-first (Flask = local UI only)

**Enterprise path is FastAPI only** (`ragevda/api.py`):
`uvicorn ragevda.api:app --host 127.0.0.1 --port 9000`
`GET /health` (model-free) · `POST /jobs` (X-API-Key) ·
`GET /jobs/{id}` · `GET /jobs/{id}/report`. OpenAPI at `/docs`,
OTEL when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Persistent SQLite job queue
(`RAGEVDA_WORKERS` pool) — no single-flight rejection.

**Flask `webapp.py` is tech-debt compat: local operator UI only**
(Inputs → Deep Analysis → Outputs, History & Trends). It mounts the same
orchestrator but MUST NOT serve production API traffic; never run both
servers on the same port. New integrations target FastAPI.

**Concurrency honesty:** gunicorn LITE = 1 worker × 2 threads → **1 audit at
a time** until a Postgres/Redis queue lands. Concurrent POSTs queue behind
the ThreadPoolExecutor (`RAGEVDA_WORKERS=1` default). Fixes "stuck at X%":
named phase markers 6→98% + 45s heartbeat + `RAGEVDA_HARVEST_TIMEOUT` 480s /
`RAGEVDA_UGC_TIMEOUT` 90s time-boxes.
