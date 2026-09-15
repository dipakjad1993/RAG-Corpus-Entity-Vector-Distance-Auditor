"""RAG-EVDA FastAPI service (enterprise API).

Replaces sync Flask single-flight with async endpoints + background workers +
API-key auth + persistent job store. Flask ``webapp.py`` remains for the local
UI; this module is the enterprise path:

    uvicorn ragevda.api:app --host 127.0.0.1 --port 9000

Endpoints: GET /health, POST /jobs (auth), GET /jobs/{id}, GET /jobs/{id}/report
OpenAPI at /docs. Jobs run in a ThreadPoolExecutor worker pool (configurable).
OTEL tracing hooks in via ``OTEL_EXPORTER_OTLP_ENDPOINT`` when installed.
"""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict

try:
    from fastapi import HTTPException
    from pydantic import BaseModel, Field
    _HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    _HAS_FASTAPI = False

from . import __version__ as _ver

_POOL = ThreadPoolExecutor(max_workers=int(os.environ.get("RAGEVDA_WORKERS", "1")))


class JobRequest(BaseModel):
    target_brand: str = Field(min_length=2)
    industry_topics: list[str] = Field(min_length=1)
    competitor_entities: list[str] = Field(min_length=1)
    crawl_depth: int = 20
    harvester: str = "multi"
    answer_harvester: str = "off"
    model_config = {"extra": "allow"}


def _require_key(x_api_key: str = "", authorization: str = "") -> None:
    if not _HAS_FASTAPI:
        return
    from .security import check_api_key
    provided = x_api_key or (authorization.replace("Bearer ", "") if authorization else "")
    if not check_api_key(provided):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def create_app():
    if not _HAS_FASTAPI:
        raise RuntimeError("fastapi not installed. pip install fastapi uvicorn")
    from fastapi import FastAPI, Header
    from . import jobs_store

    app = FastAPI(title="RAG-EVDA", version=_ver)
    WEB_OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "web_output")
    jobs_store.init(WEB_OUTPUT)

    try:  # OTEL tracing when configured
        if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
    except Exception:  # noqa: BLE001
        pass

    @app.get("/health")
    def health():
        return {"ok": True, "version": _ver}

    @app.post("/jobs")
    def submit(req: JobRequest, x_api_key: str = Header(default="")):
        _require_key(x_api_key)
        job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        job_dir = os.path.join(WEB_OUTPUT, "jobs", job_id)
        os.makedirs(job_dir, exist_ok=True)
        jobs_store.create(job_id, job_dir)
        jobs_store.update(job_id, status="queued", stage="Queued")
        _POOL.submit(_run_job, job_id, req.model_dump(), job_dir, WEB_OUTPUT)
        return {"job_id": job_id, "status": "queued"}

    @app.get("/jobs/{job_id}")
    def status(job_id: str, x_api_key: str = Header(default="")):
        _require_key(x_api_key)
        j = jobs_store.get(job_id)
        if not j:
            raise HTTPException(404, "unknown job")
        return {"job_id": job_id, **j}

    @app.get("/jobs/{job_id}/report")
    def report(job_id: str, x_api_key: str = Header(default="")):
        _require_key(x_api_key)
        import json as _j
        p = os.path.join(WEB_OUTPUT, "jobs", job_id, "report.json")
        if not os.path.exists(p):
            raise HTTPException(404, "report not ready")
        with open(p, encoding="utf-8") as fh:
            return _j.load(fh)

    return app


def _run_job(job_id: str, profile: Dict[str, Any], job_dir: str, web_output: str) -> None:
    from . import jobs_store
    try:
        jobs_store.update(job_id, status="running", stage="Initializing pipeline", progress=6)
        from .config import RunConfig
        from .orchestrator import run as _run
        cfg = RunConfig(target_brand=profile["target_brand"],
                        industry_topics=profile["industry_topics"],
                        competitor_entities=profile["competitor_entities"],
                        crawl_depth=int(profile.get("crawl_depth", 20)),
                        harvester=profile.get("harvester", "multi"),
                        output_dir=job_dir)
        # passthrough enterprise keys
        for k in ("answer_harvester", "brave_api_key", "tavily_api_key", "exa_api_key",
                  "prompt_volume", "personas", "geo_variants", "generate_llms_txt"):
            if k in profile:
                try:
                    setattr(cfg, k, profile[k])
                except Exception:  # noqa: BLE001
                    pass
        _run(cfg)
        jobs_store.update(job_id, status="done", stage="Complete", progress=100)
    except Exception as exc:  # noqa: BLE001
        jobs_store.update(job_id, status="error", stage="Failed", error=str(exc)[:2000])


app = create_app() if _HAS_FASTAPI else None
