"""Hallucination FactCheck + auto-correction loop (Profound-style, offline).

Profound FactCheck reports a ~7.9% fix rate by looping detections back into
content fixes. This module:

1. Detects candidate hallucinations offline: ghost citations (brand cited
   but unnamed), poisoning contradictions, and low-faithfulness windows.
2. Emits a per-finding **auto-correction suggestion** (concrete rewrite /
   schema / sourcing action) instead of only failing the build.
3. Attaches to eval gates output as ``advanced.eval.fixes`` so CI shows
   WHAT to fix, not just red.
"""
from __future__ import annotations

from typing import Dict, List


def factcheck_fixes(report: Dict, config) -> Dict:
    adv = report.get("advanced", {}) or {}
    findings: List[Dict] = []
    pois = adv.get("poisoning", {}) or {}
    for a in (pois.get("contradictions", []) or pois.get("alerts", []) or [])[:20]:
        findings.append({
            "type": "contradiction",
            "evidence": str(a.get("snippet", a) if isinstance(a, dict) else a)[:400],
            "url": (a.get("url", "") if isinstance(a, dict) else ""),
            "suggestion": ("Publish a canonical correction page (question H2 + 20-40 word "
                           "self-contained answer in first 50 words, table of correct specs, "
                           "Last updated + dateModified + Organization JSON-LD) and earn "
                           "one third-party citation corroborating the correction."),
        })
    ghost = adv.get("ghost_citations", {}) if isinstance(adv.get("ghost_citations"), dict) else {}
    for g in (ghost.get("items", []) if isinstance(ghost, dict) else [])[:20]:
        findings.append({
            "type": "ghost-citation",
            "evidence": str(g.get("snippet", g) if isinstance(g, dict) else g)[:400],
            "url": (g.get("url", "") if isinstance(g, dict) else ""),
            "suggestion": ("Add explicit brand naming + SameAs link on the cited page; "
                           "request the publisher name the brand (73% of mentions are "
                           "unnamed) and add a backlink to the canonical page."),
        })
    sent = adv.get("sentiment", {}) or {}
    for r in (sent.get("risk_windows", []) or [])[:10]:
        findings.append({
            "type": "negative-framing",
            "evidence": str(r.get("snippet", ""))[:400],
            "url": r.get("url", ""),
            "suggestion": ("Add an FAQ block answering the exact negative claim in 20-40 "
                           "words + Review/Product schema with visible-matched ratings; "
                           "seed one UGC reply (Reddit/YouTube) with the corrected framing."),
        })
    return {"fixes": findings, "fix_count": len(findings),
            "method": "offline contradiction+ghost+sentiment loop with rewrite suggestions"}
