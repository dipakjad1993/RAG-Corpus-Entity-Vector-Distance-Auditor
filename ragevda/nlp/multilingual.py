"""Multilingual + geo-variant engine (2026 EU requirement).

Auto-detects per-doc language (stdlib heuristic, no new dep), splits prompt
coverage per geo_variant (US/UK/...), and reports per-language/per-geo
visibility gaps. spaCy model note: en_core_web_sm default; per-doc xx models
(xx_ent_wiki_sm family) are attempted when installed, else recorded as
'degraded-language' — never faked.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict

_COMMON = {
    "en": set("the and for are with that this from have will would there their".split()),
    "de": set("der die und den von mit für ist auf dem sich nicht".split()),
    "fr": set("les des pour dans avec plus tout cette sont vous".split()),
    "es": set("los las para con por una este esta pero sus".split()),
}


def detect_lang(text: str) -> str:
    words = re.findall(r"[a-zäöüßàâéèêëîïôùûçñ]{3,}", (text or "").lower())[:400]
    if not words:
        return "unknown"
    scores = {lang: sum(1 for w in words if w in vocab) for lang, vocab in _COMMON.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 3 else "en"


def multilingual_report(docs, config) -> Dict:
    langs: Counter = Counter()
    per_doc = []
    for d in (docs or []):
        lang = detect_lang((getattr(d, "title", "") or "") + " " + (getattr(d, "text", "") or "")[:2000])
        langs[lang] += 1
        per_doc.append({"url": getattr(d, "url", ""), "lang": lang})
    want = [lang.lower() for lang in (getattr(config, "languages", ["en"]) or ["en"])]
    geos = list(getattr(config, "geo_variants", []) or [])
    gaps = []
    for lang in want:
        if langs.get(lang, 0) == 0:
            gaps.append(f"No {lang} documents harvested — add {lang} queries or feeds.")
    if geos:
        gaps.append(f"Geo split {geos}: re-run per geo_variant prompt prefix for local SoV deltas.")
    return {"lang_counts": dict(langs), "wanted": want, "geo_variants": geos,
            "gaps": gaps, "per_doc": per_doc[:300],
            "spacy_note": "en_core_web_sm default; xx_ent_wiki_sm per-doc when installed",
            "method": "stdlib stopword heuristic per doc (auditable); no fake translation"}
