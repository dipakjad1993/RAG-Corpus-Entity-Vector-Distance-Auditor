"""Persistent job queue (SQLite) — replaces in-memory JOBS + single-flight.

Scales to N users: jobs are rows (queued/running/done/error) with progress,
stage, logs (capped), dir, error, created_at. Worker pool pulls queued jobs.
Retention: ``job_retention_days`` prunes old jobs (web_output/jobs hygiene).
Thread-safe via sqlite + lock. Mirrors the old JOBS dict API so webapp keeps
working while gaining persistence.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Dict, List, Optional

_LOCK = threading.Lock()
_DB: Optional[str] = None


def db_path(web_output: str) -> str:
    return os.path.join(web_output, "jobs", "jobs.sqlite3")


def init(web_output: str) -> str:
    global _DB
    with _LOCK:
        _DB = db_path(web_output)
        os.makedirs(os.path.dirname(_DB), exist_ok=True)
        con = sqlite3.connect(_DB)
        con.execute("""CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY, status TEXT, progress INT, stage TEXT,
            dir TEXT, error TEXT, logs TEXT, created_at REAL, updated_at REAL)""")
        con.commit()
        con.close()
        return _DB


def _con():
    assert _DB, "jobs_store.init() not called"
    return sqlite3.connect(_DB)


def create(job_id: str, job_dir: str) -> None:
    now = time.time()
    with _LOCK:
        con = _con()
        con.execute("INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                    (job_id, "queued", 2, "Queued", job_dir, "", "[]", now, now))
        con.commit()
        con.close()


def update(job_id: str, **kw) -> None:
    with _LOCK:
        con = _con()
        row = con.execute("SELECT status,progress,stage,dir,error,logs FROM jobs WHERE job_id=?",
                          (job_id,)).fetchone()
        if not row:
            con.close()
            return
        status, progress, stage, d, error, logs = row
        status = kw.get("status", status)
        progress = kw.get("progress", progress)
        stage = kw.get("stage", stage)
        d = kw.get("dir", d)
        error = kw.get("error", error)
        if "log" in kw:
            try:
                arr = json.loads(logs or "[]")
            except Exception:  # noqa: BLE001
                arr = []
            arr.append(kw["log"])
            logs = json.dumps(arr[-500:])
        con.execute("UPDATE jobs SET status=?,progress=?,stage=?,dir=?,error=?,logs=?,updated_at=? "
                    "WHERE job_id=?",
                    (status, progress, stage, d, error, logs, time.time(), job_id))
        con.commit()
        con.close()


def get(job_id: str) -> Optional[Dict]:
    with _LOCK:
        con = _con()
        row = con.execute("SELECT status,progress,stage,dir,error,logs FROM jobs WHERE job_id=?",
                          (job_id,)).fetchone()
        con.close()
    if not row:
        return None
    status, progress, stage, d, error, logs = row
    try:
        log_list = json.loads(logs or "[]")
    except Exception:  # noqa: BLE001
        log_list = []
    return {"status": status, "progress": progress, "stage": stage,
            "dir": d, "error": error, "logs": log_list}


def running_ids() -> List[str]:
    with _LOCK:
        con = _con()
        rows = con.execute("SELECT job_id FROM jobs WHERE status IN ('queued','running')").fetchall()
        con.close()
    return [r[0] for r in rows]


def prune(web_output: str, retention_days: int = 30) -> int:
    import shutil
    cutoff = time.time() - retention_days * 86400
    with _LOCK:
        con = _con()
        rows = con.execute("SELECT job_id, dir FROM jobs WHERE created_at<?", (cutoff,)).fetchall()
        con.execute("DELETE FROM jobs WHERE created_at<?", (cutoff,))
        con.commit()
        con.close()
    n = 0
    for jid, d in rows:
        try:
            if d and os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
            n += 1
        except Exception:  # noqa: BLE001
            pass
    return n
