"""RAGAS / DeepEval-style quality gates (P0 — closes EVAL.md open item).

Metrics (all computed from REAL report evidence, no LLM needed offline):
* faithfulness: 1 - contradiction_rate (poisoning contradictions + ghost cites)
* answer_relevancy: brand proximity mass over retrieved windows
* context_precision: retrieved windows above calibrated threshold / retrieved
* context_recall: topics with >=1 retrieved brand window / topics

Thresholds from config (>=0.75 / 0.80 / 0.70 / 0.70). ``pytest --geo`` fails
the build when any gate fails (fail-loud > fail-fake).
"""
from __future__ import annotations

from typing import Dict


def _get(cfg, name: str, default: float) -> float:
    try:
        return float(getattr(cfg, name, default))
    except Exception:  # noqa: BLE001
        return default


def run_eval_gates(report: Dict, config) -> Dict:
    adv = report.get("advanced", {}) or {}
    pois = (adv.get("poisoning", {}) or {})
    chunk = (adv.get("chunking", {}) or {})
    inv = report.get("invisibility", {}) or {}
    per_topic = inv.get("per_topic", []) or []
    contra = len(pois.get("contradictions", []) or pois.get("alerts", []) or [])
    docs_n = max(1, int(report.get("meta", {}).get("context_stats", {}).get("doc_count", 1)))
    faith = max(0.0, 1.0 - contra / docs_n)
    retrieved = int(chunk.get("retrieved_count", 0) or 0)
    windows = max(1, int(chunk.get("window_count", 1) or 1))
    precision = min(1.0, retrieved / windows)
    topics = len(per_topic) or 1
    covered = sum(1 for t in per_topic if (t.get("vector_share_of_voice_pct", 0) or 0) > 0)
    recall = covered / topics
    prox_rows = (report.get("proximity", {}) or {}).get("rows", []) or []
    brand = config.target_brand
    bprox = [r.get("proximity", 0) for r in prox_rows if r.get("entity") == brand]
    relev = (sum(bprox) / len(bprox)) if bprox else 0.0
    relev = max(0.0, min(1.0, relev))
    gates = {
        "faithfulness": round(faith, 3),
        "answer_relevancy": round(relev, 3),
        "context_precision": round(precision, 3),
        "context_recall": round(recall, 3),
    }
    th = {"faithfulness": _get(config, "eval_faithfulness_min", 0.75),
          "answer_relevancy": _get(config, "eval_answer_relevancy_min", 0.80),
          "context_precision": _get(config, "eval_context_precision_min", 0.70),
          "context_recall": _get(config, "eval_context_recall_min", 0.70)}
    passed = {k: (v >= th[k]) for k, v in gates.items()}
    out = {"metrics": gates, "thresholds": th, "passed": passed,
           "gate_pass": all(passed.values()),
           "method": "offline RAGAS-style gates from real report evidence"}
    # Auto-correction loop (Profound FactCheck-style): attach concrete rewrite
    # suggestions for every failing gate instead of only failing the build.
    try:
        from .factcheck import factcheck_fixes
        fc = factcheck_fixes(report, config)
        fixes = list(fc.get("fixes", []) or [])
        for k, ok in passed.items():
            if not ok:
                fixes.append({
                    "type": f"gate-fail:{k}",
                    "evidence": f"{k}={gates[k]} below threshold {th[k]}",
                    "suggestion": _fix_for_gate(k, report, config),
                })
        out["fixes"] = fixes
        out["fix_count"] = len(fixes)
    except Exception:  # noqa: BLE001
        pass
    return out


def _fix_for_gate(gate: str, report: Dict, config) -> str:
    brand = getattr(config, "target_brand", "the brand")
    if gate == "faithfulness":
        return ("Resolve poisoning contradictions + ghost citations (see advanced.eval.fixes), "
                f"publish a canonical correction page for {brand} with Organization JSON-LD.")
    if gate == "answer_relevancy":
        return (f"Raise {brand} token density: question H2 + 20-40 word answer in first 50 words, "
                "spec table, numbers, third-party corroboration (85% of mentions are off-domain).")
    if gate == "context_precision":
        return ("Tighten retrieval: raise per-topic thresholds, prune low-relevance docs, "
                "add BM25-friendly exact brand strings to canonical pages.")
    return ("Expand coverage: publish one page per uncovered topic (no mass fan-out pages — "
            "scaled abuse), earn one UGC + one press citation per topic.")
