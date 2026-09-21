"""EVAL v2 protocol — hand-labeled citation-gap precision/recall (P1 depth).

v1 gates (faithfulness >= 0.75, answer relevancy >= 0.80, context
precision/recall >= 0.70) fail the build on hallucinated math. v2 adds
*external validity*: 50 hand-labeled docs scored for citation-gap
correctness, compared against the RAGAS-style gate outputs.

This module is the *scoring harness* (stdlib only). The labels live in
``eval/labels_v2.sample.json`` (schema + 5 worked examples); teams extend to
50 with their own brand docs. No network, no models — runs in fast CI.

Schema per label:
  {"doc_id": str, "url": str, "entity": str,
   "human": "linked" | "unlinked" | "omitted",
   "system": "linked" | "unlinked" | "omitted"}
"""
from __future__ import annotations

import json
from typing import Dict, List


LABELS = ("linked", "unlinked", "omitted")


def precision_recall(labels: List[Dict]) -> Dict:
    """Per-class precision/recall/F1 + macro F1 over hand labels."""
    per = {}
    for cls in LABELS:
        tp = sum(1 for r in labels
                 if r.get("human") == cls and r.get("system") == cls)
        fp = sum(1 for r in labels
                 if r.get("human") != cls and r.get("system") == cls)
        fn = sum(1 for r in labels
                 if r.get("human") == cls and r.get("system") != cls)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per[cls] = {"tp": tp, "fp": fp, "fn": fn,
                    "precision": round(prec, 3),
                    "recall": round(rec, 3), "f1": round(f1, 3)}
    macro_f1 = round(sum(v["f1"] for v in per.values()) / len(per), 3)
    acc = (sum(1 for r in labels if r.get("human") == r.get("system"))
           / len(labels)) if labels else 0.0
    return {"per_class": per, "macro_f1": macro_f1,
            "accuracy": round(acc, 3), "n": len(labels),
            "method": "hand-labeled citation-gap audit (v2); 50-doc target"}


def load_labels(path: str) -> List[Dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "labels" in data:
        return list(data["labels"])
    return list(data)
