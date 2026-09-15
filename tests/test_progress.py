"""Progress heartbeats: silent CPU phases must move the web bar monotonically."""
import os

import pytest


def _prog(msgs):
    # Web tests need flask, which CI's light fast-test env deliberately omits:
    # skip (don't fail) when it isn't installed.
    pytest.importorskip("flask", reason="web progress tests need flask")
    from ragevda import webapp as w
    job = {"status": "running", "progress": 0, "stage": ""}
    out = []
    for m in msgs:
        w._progress_from_msg(job, m)
        out.append(job["progress"])
    return out, job


def test_heartbeat_keywords_bump_progress():
    prog, _ = _prog([
        "starting audit run",
        "building analysis context for 200 documents",
        "chunked 50/200 docs (300 chunks so far)",
        "embedded 256/1200 chunks",
        "scanned mentions 25/200 docs",
        "entity centroid: TestBrand (40 chunks)",
        "context built: 3 entities, 2 topics",
        "scoring sentiment for 300 mention windows (150 unique)",
        "sentiment scored 150/150 windows",
        "wrote JSON report",
    ])
    assert prog == sorted(prog), f"progress must never go backwards: {prog}"
    assert prog[2] == 76
    assert prog[4] == 81  # max(embedded 81, scanned-mentions 78): never backwards
    assert prog[5] == 84
    assert prog[7] == 90
    assert prog[8] == 92
    assert prog[-1] == 94


def test_done_job_ignores_late_logs():
    pytest.importorskip("flask", reason="web progress tests need flask")
    from ragevda import webapp as w
    job = {"status": "done", "progress": 100, "stage": "Complete"}
    w._progress_from_msg(job, "fetching something")
    assert job["progress"] == 100
    assert job["stage"] == "Complete"


def test_fetch_env_overrides(monkeypatch):
    from ragevda.config import RunConfig
    monkeypatch.setenv("RAGEVDA_FETCH_TIMEOUT", "8")
    monkeypatch.setenv("RAGEVDA_MAX_CONCURRENCY", "16")
    c = RunConfig(target_brand="TestBrand", industry_topics=["analytics software"],
                  competitor_entities=["RivalOne"])
    c.apply_env_overrides()
    assert c.request_timeout == 8
    assert c.max_concurrency == 16
    monkeypatch.setenv("RAGEVDA_FETCH_TIMEOUT", "bogus")
    c.apply_env_overrides()  # never raises on bad input
    assert c.request_timeout == 8
    assert "RAGEVDA_FETCH_TIMEOUT" in os.environ
