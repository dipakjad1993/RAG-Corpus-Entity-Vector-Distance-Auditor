"""Prompt library + persona expansion (P0).

Forward-tracks REAL prompts clients care about (informational / transactional /
comparison frames x personas x geo variants), repeated for probabilistic noise.
Replaces relying solely on reverse-engineered synthetic queries.
"""
from __future__ import annotations

import os
from typing import Dict, List

import yaml


def load_library(path: str = "") -> Dict:
    default = os.path.join(os.path.dirname(__file__), "prompts.yaml")
    p = path or default
    try:
        with open(p, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:  # noqa: BLE001
        return {}


def build_prompts(config, library: Dict | None = None) -> List[Dict]:
    """Expand library frames into concrete prompts.

    Returns ``[{prompt, frame, persona, topic, geo, repeat}]``. Volume =
    topics x frames x personas x geo-variants x prompt_volume.
    """
    lib = library if library is not None else load_library(
        getattr(config, "prompt_library", "") or "")
    frames: Dict[str, List[str]] = lib.get("frames", {}) or {}
    personas: List[str] = getattr(config, "personas", ["default"]) or ["default"]
    want_frames: List[str] = getattr(config, "prompt_frames",
                                     ["informational", "transactional", "comparison"]) or []
    geos: List[str] = list(getattr(config, "geo_variants", []) or [])
    if getattr(config, "locality", None):
        geos = [config.locality] + geos
    geos = geos or [""]
    vol = max(1, int(getattr(config, "prompt_volume", 5)))
    brand = config.target_brand
    comps = list(config.competitor_entities)
    out: List[Dict] = []
    for topic in config.industry_topics:
        for frame in want_frames:
            for tpl in frames.get(frame, []):
                for persona in personas:
                    for geo in geos:
                        base = tpl.format(topic=topic, brand=brand,
                                          persona=persona, geo=geo or "my area",
                                          competitor=comps[0] if comps else "")
                        for r in range(vol):
                            out.append({"prompt": base, "frame": frame,
                                        "persona": persona, "topic": topic,
                                        "geo": geo, "repeat": r})
    # de-dupe identical prompts (keep first repeat count metadata)
    seen, uniq = set(), []
    for p in out:
        key = (p["prompt"], p["persona"], p["geo"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq
