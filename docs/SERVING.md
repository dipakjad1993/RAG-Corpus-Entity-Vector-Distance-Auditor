# Serving — single API path (2026)

**Enterprise path: FastAPI only** (`ragevda/api.py`):
`uvicorn ragevda.api:app --host 127.0.0.1 --port 9000`
Endpoints: `GET /health`, `POST /jobs` (API key), `GET /jobs/{id}`,
`GET /jobs/{id}/report`. OpenAPI at `/docs`.

**Local UI:** `ragevda/webapp.py` (Flask) is the local operator UI. It mounts
the same orchestrator + job store — it does NOT serve the API on :9000 in
production. Never run both servers on the same port.

**Concurrency honesty:** Gunicorn LITE = 1 worker × 2 threads → **1 audit at a
time** until a Postgres/Redis queue lands. Concurrent POSTs queue behind the
ThreadPoolExecutor (`RAGEVDA_WORKERS=1` default).
