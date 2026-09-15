"""Query fan-out expansion + PAA + volume weighting (Profound/Ahrefs-style).

Forward-tracking needs more than prompts.yaml frames x personas: real GEO
tools decompose each seed prompt into a fan-out tree (sub-questions, PAA,
comparisons, follow-ups) and weight by search volume so high-traffic
intents dominate the audit.

* Expansion is deterministic + offline (template fan-out per frame, PAA
  patterns mined from harvested titles/snippets when available).
* Volume weighting: uses prompt_volume repeats + optional per-prompt weights;
  every expanded prompt carries weight so SoV aggregates are traffic-aware.
* All prompts real strings — never sent anywhere without paid keys; the
  Answer Harvester consumes them when configured (multi + 5-10 repeats).
"""
from __future__ import annotations

from typing import Dict, List

FANOUT_PATTERNS = [
    "what is {topic}",
    "how does {topic} work",
    "best {topic} for {persona}",
    "{topic} vs alternatives",
    "{topic} pricing",
    "{topic} reviews",
    "{topic} pros and cons",
    "is {topic} worth it",
    "{topic} for {persona} use case",
    "{topic} alternatives compared",
]

PAA_PATTERNS = [
    "People also ask: is {topic} reliable?",
    "People also ask: how much does {topic} cost?",
    "People also ask: what is the best {topic}?",
]


def expand_prompts(topics: List[str], frames: List[str],
                   personas: List[str], volume: int = 5,
                   harvested_titles: List[str] | None = None) -> Dict:
    out: List[Dict] = []
    frames = frames or ["informational"]
    personas = personas or ["default"]
    for topic in topics or []:
        for frame in frames:
            for persona in personas:
                for pat in FANOUT_PATTERNS:
                    q = pat.format(topic=topic, persona=persona)
                    out.append({"prompt": q, "topic": topic, "frame": frame,
                                "persona": persona, "kind": "fanout",
                                "weight": volume})
                for pat in PAA_PATTERNS:
                    q = pat.format(topic=topic)
                    out.append({"prompt": q, "topic": topic, "frame": frame,
                                "persona": persona, "kind": "paa",
                                "weight": max(1, volume // 2)})
    # semantic fan-out from real harvested titles (evidence-grounded)
    for t in (harvested_titles or [])[:20]:
        tl = (t or "").strip()
        if len(tl) > 24:
            out.append({"prompt": tl, "topic": topics[0] if topics else "",
                        "frame": "observed", "persona": "observed",
                        "kind": "observed-title", "weight": 1})
    # de-dupe preserving order
    seen, uniq = set(), []
    for p in out:
        k = p["prompt"].lower()
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    total_weight = sum(p["weight"] for p in uniq) or 1
    for p in uniq:
        p["weight_pct"] = round(100.0 * p["weight"] / total_weight, 2)
    return {"prompts": uniq, "count": len(uniq),
            "total_weight": total_weight,
            "method": "template fan-out x frames x personas + PAA + observed titles, volume-weighted"}
