"""Semantic Drift Tracking & Time-Series Database.

AI search engines re-index and change vector positions continuously.  A single
audit is a snapshot; teams need daily/weekly *deltas* to answer: "did my vector
distance to Topic X drift after Competitor B's whitepaper?"

This module persists every run's comparable metrics into a durable
time-series store (DuckDB, zero cost) so that each new audit can:

  * snapshot brand proximity, invisibility and Vector Share of Voice per topic;
  * compute the *drift* (delta) versus the most recent prior run of the same
    brand + topic set;
  * alert when a metric moved beyond a tunable tolerance band (e.g. proximity
    drifted > X farther away, or invisibility jumped).

Everything is computed from real run data written by the orchestrator; the DB
is written next to the run outputs (``drift_timeseries.duckdb``) so every job
carries its own full history.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

from ..utils import get_logger

logger = get_logger("ragevda.analysis.drift")


class DriftStore:
    """DuckDB-backed time-series of per-run comparable metrics."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.con = None
        self.available = False
        try:
            import duckdb  # type: ignore
            os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
            self.con = duckdb.connect(db_path)
            self.available = True
            self._init_schema()
        except Exception as exc:  # noqa: BLE001
            logger.warning("drift store unavailable (%s); drift=0", exc)
            self.available = False

    def _init_schema(self):
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS drift_snapshots (
                job_id VARCHAR,
                generated_at VARCHAR,
                brand VARCHAR,
                topic VARCHAR,
                proximity DOUBLE,
                invisibility_pct DOUBLE,
                sov_pct DOUBLE,
                threshold DOUBLE,
                relevant_docs INTEGER
            )
        """)
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_drift_brand_topic
            ON drift_snapshots(brand, topic, generated_at)
        """)

    def snapshot(self, job_id: str, generated_at: str, brand: str,
                 per_topic: List[Dict]) -> None:
        if not self.available:
            return
        rows = [
            (job_id, generated_at, brand, t.get("topic", ""),
             float(t.get("proximity", 0.0)),
             float(t.get("topic_invisibility_pct", 0.0)),
             float(t.get("vector_share_of_voice_pct", 0.0)),
             float(t.get("threshold_used", 0.0)),
             int(t.get("relevant_docs", 0)))
            for t in per_topic
        ]
        if not rows:
            return
        self.con.executemany(
            "INSERT INTO drift_snapshots VALUES (?,?,?,?,?,?,?,?,?)", rows)

    def latest_for(self, brand: str, topic: str,
                   exclude_job: Optional[str] = None) -> Optional[Dict]:
        """Return the most recent prior snapshot for brand+topic."""
        if not self.available:
            return None
        q = ("SELECT job_id, generated_at, proximity, invisibility_pct, "
             "sov_pct, threshold, relevant_docs FROM drift_snapshots "
             "WHERE brand=? AND topic=?")
        params: List = [brand, topic]
        if exclude_job:
            q += " AND job_id != ?"
            params.append(exclude_job)
        q += " ORDER BY generated_at DESC LIMIT 1"
        row = self.con.execute(q, params).fetchone()
        if not row:
            return None
        return {
            "job_id": row[0], "generated_at": row[1], "proximity": row[2],
            "invisibility_pct": row[3], "sov_pct": row[4],
            "threshold": row[5], "relevant_docs": row[6],
        }

    def history(self, brand: str, topic: str, limit: int = 30) -> List[Dict]:
        if not self.available:
            return []
        rows = self.con.execute(
            "SELECT job_id, generated_at, proximity, invisibility_pct, sov_pct "
            "FROM drift_snapshots WHERE brand=? AND topic=? "
            "ORDER BY generated_at DESC LIMIT ?",
            [brand, topic, limit]).fetchall()
        return [
            {"job_id": r[0], "generated_at": r[1], "proximity": r[2],
             "invisibility_pct": r[3], "sov_pct": r[4]}
            for r in rows
        ]

    def history_topic(self, brand: str, topic: str) -> List[Dict]:
        """Full chronological history (ascending) of a brand+topic series."""
        if not self.available:
            return []
        rows = self.con.execute(
            "SELECT job_id, generated_at, proximity, invisibility_pct, sov_pct, "
            "relevant_docs FROM drift_snapshots WHERE brand=? AND topic=? "
            "ORDER BY generated_at ASC",
            [brand, topic]).fetchall()
        return [
            {"job_id": r[0], "generated_at": r[1], "proximity": r[2],
             "invisibility_pct": r[3], "sov_pct": r[4],
             "relevant_docs": r[5]}
            for r in rows
        ]

    def close(self) -> None:
        if self.con is not None and self.available:
            self.con.close()


def _linear_trend(values: List[float]) -> float:
    """Slope of a simple linear regression (y on index) over a time series.

    Positive slope => the metric is rising over time; negative => falling.
    Returns 0.0 when there are fewer than 2 points or zero variance in x.
    """
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, values))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


def _zscore(x: float, series: List[float]) -> float:
    """Z-score of x against a reference series (how anomalous is this point)."""
    if len(series) < 2:
        return 0.0
    m = sum(series) / len(series)
    var = sum((v - m) ** 2 for v in series) / (len(series) - 1)
    sd = var ** 0.5
    if sd == 0:
        return 0.0
    return (x - m) / sd


def _two_tailed_p(z: float) -> float:
    """Two-tailed p-value for a z-score via the standard normal CDF.

    Uses a maximally-accurate Abramowitz & Stegun 26.2.17 rational
    approximation (|error| < 7.5e-8), so each drift alert carries a real
    statistical significance level rather than a bare heuristic cutoff.
    """
    if not z or abs(z) > 38:
        return 0.0 if z else 1.0
    z = abs(z)
    t = 1.0 / (1.0 + 0.2316419 * z)
    import math as _math
    phi = _math.exp(-z * z / 2.0) / 2.506628274631  # N(0,1) pdf (was *sqrt2pi: fixed)
    p_hi = 1.0 - (
        0.319381530 * t
        - 0.356563782 * t * t
        + 1.781477937 * t * t * t
        - 1.821255978 * t * t * t * t
        + 1.330274429 * t * t * t * t * t
    ) * phi
    p_hi = max(0.0, min(1.0, p_hi))
    return round(2.0 * (1.0 - p_hi), 6)


def compute_drift(store: DriftStore, job_id: str, generated_at: str,
                  config, proximity_rows: List[Dict],
                  invisibility_topic: List[Dict],
                  drift_tolerance: float = 0.05) -> Dict:
    """Snapshot current run and compute per-topic drift vs the prior run.

    ``drift_tolerance`` (default 0.05 / 5 pp) is the band under which a change
    is considered noise. Returns a drift report with deltas + alerts.
    """
    brand = config.target_brand
    # Build per-topic snapshot from real data.
    prox_by_topic: Dict[str, float] = {}
    for r in proximity_rows:
        if r["entity"] == brand:
            prox_by_topic[r["topic"]] = r["proximity"]

    snap: List[Dict] = []
    for t in invisibility_topic:
        snap.append({
            "topic": t["topic"],
            "proximity": prox_by_topic.get(t["topic"], 0.0),
            "topic_invisibility_pct": t.get("topic_invisibility_pct", 0.0),
            "vector_share_of_voice_pct": t.get("vector_share_of_voice_pct", 0.0),
            "threshold_used": t.get("threshold_used", 0.0),
            "relevant_docs": t.get("relevant_docs", 0),
        })

    store.snapshot(job_id, generated_at, brand, snap)

    per_topic_drift: List[Dict] = []
    alerts: List[Dict] = []
    for s in snap:
        prior = store.latest_for(brand, s["topic"], exclude_job=job_id)
        history = store.history_topic(brand, s["topic"])
        # reference series for anomaly detection (all historical points of the
        # same metric, in ascending chronological order)
        hist_prox = [h["proximity"] for h in history]
        hist_inv = [h["invisibility_pct"] for h in history]
        hist_sov = [h["sov_pct"] for h in history]
        entry = {
            "topic": s["topic"],
            "proximity": round(s["proximity"], 4),
            "invisibility_pct": s["topic_invisibility_pct"],
            "sov_pct": s["vector_share_of_voice_pct"],
            "relevant_docs": s["relevant_docs"],
            "proximity_delta": 0.0,
            "invisibility_delta": 0.0,
            "sov_delta": 0.0,
            "has_prior": bool(prior),
            "prior_generated_at": prior["generated_at"] if prior else None,
            "data_points": len(history),
            "trend_proximity_per_run": round(_linear_trend(hist_prox), 4),
            "trend_invisibility_per_run": round(_linear_trend(hist_inv), 3),
            "trend_sov_per_run": round(_linear_trend(hist_sov), 3),
            "forecast_next_proximity": forecast_next(hist_prox + [s["proximity"]]),
            "anomaly": False,
            "anomaly_metric": None,
        }
        if prior:
            entry["proximity_delta"] = round(s["proximity"] - prior["proximity"], 4)
            entry["invisibility_delta"] = round(
                s["topic_invisibility_pct"] - prior["invisibility_pct"], 4)
            entry["sov_delta"] = round(
                s["vector_share_of_voice_pct"] - prior["sov_pct"], 4)

            # Drift alert: brand moved farther from topic, invisibility rose,
            # or share-of-voice fell beyond tolerance -- OR a z-score based
            # anomaly is detected against the real historical series.
            prox_z = _zscore(s["proximity"], hist_prox)
            inv_z = _zscore(s["topic_invisibility_pct"], hist_inv)
            sov_z = _zscore(s["vector_share_of_voice_pct"], hist_sov)
            triggered = False
            reason_parts = []
            if entry["proximity_delta"] < -drift_tolerance:
                triggered = True
                reason_parts.append(
                    f"proximity fell {entry['proximity_delta']:+.3f}")
            if entry["invisibility_delta"] > drift_tolerance * 10:
                triggered = True
                reason_parts.append(
                    f"invisibility up {entry['invisibility_delta']:+.1f} pp")
            if entry["sov_delta"] < -drift_tolerance * 10:
                triggered = True
                reason_parts.append(
                    f"share-of-voice down {entry['sov_delta']:+.1f} pp")
            # statistical anomaly (|z| >= 2 against >3 historic points)
            if len(hist_prox) >= 4:
                if abs(prox_z) >= 2.0:
                    triggered = True
                    entry["anomaly"] = True
                    entry["anomaly_metric"] = "proximity"
                    reason_parts.append(
                        f"proximity z-score {prox_z:+.2f} (anomalous)")
                if abs(inv_z) >= 2.0:
                    triggered = True
                    entry["anomaly"] = True
                    entry["anomaly_metric"] = "invisibility"
                    reason_parts.append(
                        f"invisibility z-score {inv_z:+.2f} (anomalous)")
                if abs(sov_z) >= 2.0:
                    triggered = True
                    entry["anomaly"] = True
                    entry["anomaly_metric"] = "sov"
                    reason_parts.append(
                        f"SoV z-score {sov_z:+.2f} (anomalous)")
            if triggered:
                alerts.append({
                    "topic": s["topic"],
                    "reason": "; ".join(reason_parts) or "metric moved beyond tolerance",
                    "proximity_delta": entry["proximity_delta"],
                    "invisibility_delta": entry["invisibility_delta"],
                    "sov_delta": entry["sov_delta"],
                    "proximity_zscore": round(prox_z, 3),
                    "invisibility_zscore": round(inv_z, 3),
                    "sov_zscore": round(sov_z, 3),
                    "proximity_pvalue": _two_tailed_p(prox_z),
                    "invisibility_pvalue": _two_tailed_p(inv_z),
                    "sov_pvalue": _two_tailed_p(sov_z),
                    "history_points": len(hist_prox),
                })
        per_topic_drift.append(entry)

    return {
        "job_id": job_id,
        "generated_at": generated_at,
        "store_available": store.available,
        "drift_tolerance": drift_tolerance,
        "per_topic": per_topic_drift,
        "alerts": alerts,
        "db_path": store.db_path,
        "forecast": {e["topic"]: {"next_proximity": e.get("forecast_next_proximity"),
                                  "trend_per_run": e.get("trend_proximity_per_run")}
                     for e in per_topic_drift},
    }


def forecast_next(values: List[float]) -> Optional[float]:
    """ETS-lite forecast: last value + slope (Prophet-style trend when scipy absent).

    Uses the linear-regression slope over the series; returns None when <3 points.
    """
    if len(values) < 3:
        return None
    slope = _linear_trend(values)
    return round(values[-1] + slope, 4)


def send_alert_webhook(webhook_url: str, alerts: List[Dict], job_id: str) -> bool:
    """POST drift alerts to a Slack-compatible webhook. Fail-open (False on error)."""
    if not webhook_url or not alerts:
        return False
    try:
        import httpx
        from ..utils import assert_url_allowed
        assert_url_allowed(webhook_url)
        text = f"RAG-EVDA drift alerts ({job_id}): " + "; ".join(
            f"{a.get('topic')}: {a.get('reason')}" for a in alerts[:10])
        with httpx.Client(timeout=15) as c:
            r = c.post(webhook_url, json={"text": text})
            return 200 <= r.status_code < 300
    except Exception as exc:  # noqa: BLE001
        logger.warning("drift webhook failed: %s", exc)
        return False
