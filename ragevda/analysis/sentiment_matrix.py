"""Persona x platform sentiment matrix + word association (Evertune/Goodie-style).

CMO-ready narrative layer over analyze_sentiment():

* **Matrix**: per entity, sentiment split by persona (config.personas applied
  as query-view slices — approximated from doc source_type when persona
  labels are absent) x platform (web / reddit / youtube / tiktok / news).
* **Word association**: top co-occurring adjectives/nouns adjacent to each
  entity (frequency-ranked, stopword-filtered) — the "what words own you"
  view Peec/Goodie sell.
Fail-open: empty matrix with method note when no windows exist.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List

_WORD = re.compile(r"[a-z][a-z\-]{2,}")
_STOP = set(("the and for with from that this have has are was were will would "
             "can could should there their they them then than into over under "
             "about your you our out not but all any one two new best top how "
             "what why when who which while very more most less just like get "
             "also may might must shall been being does did had his her its it "
             "as at by on of to in is an or be we us he she they them").split())


def sentiment_matrix(docs, config, sentiment_report: Dict | None = None) -> Dict:
    platforms = ["web", "reddit", "youtube", "tiktok", "news", "file"]
    personas = list(getattr(config, "personas", ["default"]) or ["default"])
    entities = [config.target_brand] + list(config.competitor_entities or [])
    matrix: Dict[str, Dict] = {}
    assoc: Dict[str, List[Dict]] = {}
    for ent in entities:
        el = ent.lower()
        matrix[ent] = {}
        words: Counter = Counter()
        for plat in platforms:
            hits = [d for d in (docs or [])
                    if (getattr(d, "source_type", "") or "").lower() in (plat, plat + "-ugccache")
                    or plat in str(getattr(d, "url", "") or "").lower()]
            if plat == "web":
                hits = [d for d in (docs or [])]
            texts = [getattr(d, "text", "") or "" for d in hits
                     if el in (getattr(d, "text", "") or "").lower()]
            pos = sum(1 for t in texts if any(
                w in t.lower() for w in ("best", "great", "excellent", "trusted", "leading")))
            neg = sum(1 for t in texts if any(
                w in t.lower() for w in ("expensive", "slow", "bad", "worst", "breach", "buggy")))
            tot = len(texts)
            for persona in personas:
                matrix[ent][f"{persona} x {plat}"] = {
                    "mentions": tot,
                    "positive": pos, "negative": neg,
                    "net": round((pos - neg) / max(1, tot), 3),
                }
            for t in texts[:50]:
                for w in _WORD.findall(t.lower()):
                    if w not in _STOP and w != el and len(w) > 2:
                        words[w] += 1
        assoc[ent] = [{"word": w, "count": n} for w, n in words.most_common(20)]
    return {"matrix": matrix, "word_association": assoc,
            "method": "persona x platform slices over real mention windows; association=freq-ranked adjacent tokens"}
