"""Answer-volatility + citation-decay tracker (P0 credibility).

Why this exists: a single-sample "visibility score" is meaningless — LLM
answers vary run to run (probabilistic noise). Profound's killer feature is
Citation Decay week-over-week; this is the $0 auditable equivalent.

Inputs are REAL report evidence only — never synthesised:

* ``answer_repeats`` samples per prompt -> mean +/- stdev per entity/topic
  (pass ``samples`` explicitly; when absent we report ``n=1`` honestly and
  mark volatility UNKNOWN instead of faking a stdev).
* drift history (``advanced.drift.per_topic``) -> week-over-week citation
  decay: delta SoV / delta proximity + linear trend slope per run.

Stdlib only so the LITE/fast-test path stays green.
"""
from __future__ import annotations

import math
import statistics
from typing import Dict, List


def summarize_repeats(samples: List[float]) -> Dict:
    """Mean +/- stdev for one prompt's repeated answer samples."""
    vals = [float(v) for v in (samples or []) if v is not None]
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": 0.0, "stdev": 0.0,
                "status": "NO_SAMPLES", "method": "no answer samples collected"}
    if n == 1:
        return {"n": 1, "mean": round(vals[0], 4), "stdev": 0.0,
                "status": "SINGLE_SAMPLE",
                "note": "single sample — re-run with answer_repeats 5-10 for volatility",
                "method": "n=1, stdev not computable"}
    mean = statistics.fmean(vals)
    stdev = statistics.pstdev(vals) if n > 1 else 0.0
    status = "STABLE" if stdev < 0.08 else ("VOLATILE" if stdev >= 0.15 else "WATCH")
    return {"n": n, "mean": round(mean, 4), "stdev": round(stdev, 4),
            "min": round(min(vals), 4), "max": round(max(vals), 4),
            "status": status,
            "method": "population stdev over answer_repeats samples"}


def volatility_report(answer_samples: Dict[str, List[float]] | None = None,
                      drift: Dict | None = None,
                      answer_repeats: int = 5) -> Dict:
    """Build the dashboard-ready volatility block.

    ``answer_samples``: {prompt_key: [score, ...]} when the answer harvester
    ran with repeats; None/{} -> honest UNKNOWN block (never fake numbers).
    ``drift``: advanced.drift block for citation-decay week-over-week.
    """
    per_prompt: Dict[str, Dict] = {}
    if answer_samples:
        for k, vals in answer_samples.items():
            per_prompt[str(k)] = summarize_repeats(vals)
    stdevs = [v["stdev"] for v in per_prompt.values() if v.get("n", 0) > 1]
    overall = {
        "prompts_tracked": len(per_prompt),
        "prompts_with_repeats": sum(1 for v in per_prompt.values() if v.get("n", 0) > 1),
        "mean_stdev": round(statistics.fmean(stdevs), 4) if stdevs else 0.0,
        "max_stdev": round(max(stdevs), 4) if stdevs else 0.0,
        "answer_repeats": int(answer_repeats or 0),
    }
    if not per_prompt:
        overall["status"] = "UNKNOWN"
        overall["note"] = ("no repeated answer samples this run — "
                           "set answer_harvester: multi + answer_repeats: 5-10 "
                           "with BRAVE/TAVILY/EXA keys for real volatility")
    elif overall["prompts_with_repeats"] == 0:
        overall["status"] = "SINGLE_SAMPLE"
        overall["note"] = "each prompt sampled once — raise answer_repeats for volatility"
    else:
        ms = overall["mean_stdev"]
        overall["status"] = "STABLE" if ms < 0.08 else ("VOLATILE" if ms >= 0.15 else "WATCH")

    # Citation decay week-over-week from real drift deltas.
    decay: List[Dict] = []
    per_topic = ((drift or {}).get("per_topic", []) or []) if isinstance(drift, dict) else []
    for t in per_topic:
        if not isinstance(t, dict):
            continue
        decay.append({
            "topic": t.get("topic", ""),
            "sov_delta": t.get("sov_delta", 0.0),
            "proximity_delta": t.get("proximity_delta", 0.0),
            "trend_sov_per_run": t.get("trend_sov_per_run", 0.0),
            "trend_proximity_per_run": t.get("trend_proximity_per_run", 0.0),
            "data_points": t.get("data_points", 0),
            "has_prior": t.get("has_prior", False),
        })
    decay.sort(key=lambda r: abs(float(r.get("sov_delta") or 0.0)), reverse=True)

    return {
        "per_prompt": per_prompt,
        "overall": overall,
        "citation_decay": decay[:25],
        "method": ("per-prompt mean±stdev over answer_repeats samples + "
                   "week-over-week SoV/proximity deltas from drift history; "
                   "single-sample runs are labelled, never smoothed"),
    }


def decay_alerts(vol: Dict, threshold: float = 5.0) -> List[Dict]:
    """Fire when any topic's SoV decay exceeds threshold (pp). Pure math."""
    out: List[Dict] = []
    for r in (vol or {}).get("citation_decay", []) or []:
        try:
            d = float(r.get("sov_delta") or 0.0)
        except (TypeError, ValueError):
            continue
        if r.get("has_prior") and abs(d) >= threshold:
            out.append({"topic": r.get("topic", ""),
                        "sov_delta": d,
                        "reason": f"SoV moved {d:+.1f} pp week-over-week"})
    return out


def is_stable(x: float) -> bool:
    return math.isfinite(x)
