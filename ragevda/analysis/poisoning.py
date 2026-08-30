"""Vector Poisoning / Negative SEO Detection.

Low-quality external sites occasionally create bad entity associations with a
brand in vector space (spammy co-citations, link-farm pages that mention the
brand beside gambling/virus/loan terms, doorway pages, etc.).  Because RAG
engines embed co-occurrence, those associations can drag a brand's centroid
toward junk topics and hurt retrieval relevance.

This detector scores every harvested source for *poisoning risk*:

  * spam / doorway signals: thin content, excessive links, aggressive
    monetisation terms, machine-generated phrasing;
  * off-topic entity adjacency: a source that co-cites the brand with toxic or
    unrelated concept clusters (debt, casino, VPN, weight-loss, "buy followers");
  * authority deficit: low outbound diversity (a page that only exists to link
    out), no body substance after cleaning.

The output is a risk-ranked list plus per-entity poisoning exposure, so a team
can disavow / disassociate before it surfaces in AI answers.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Dict, List

from ..utils import get_logger

logger = get_logger("ragevda.analysis.poisoning")

# High-risk concept clusters often bought on low-tier link farms.
_TOXIC_CLUSTERS = [
    {"gambling", "casino", "bet", "slot", "poker", "lottery"},
    {"debt", "loan", "payday", "mortgage-refinance", "credit-score"},
    {"cbd", "viagra", "weight-loss", "keto", "diet-pill", "supplement"},
    {"buy-followers", "cheap-backlinks", "seo-packages", "guest-post-buy"},
    {"vpn", "crack", "serial-key", "torrent", "download-free"},
    {"adult", "dating", "escort", "hookup"},
    {"forex", "binary-options", "make-money-fast", "passive-income-scam"},
]
_LINK_WORDS = {"click here", "read more", "check this out", "visit website",
               "buy now", "order now", "limited offer", "act now"}

_HTML_LINK_RE = re.compile(r'''<a\b[^>]*href=["']([^"']+)''', re.IGNORECASE)


def _link_count(raw_html: str) -> int:
    if not raw_html:
        return 0
    return len(_HTML_LINK_RE.findall(raw_html))


def _toxic_hits(text: str) -> int:
    low = text.lower()
    hits = 0
    for cluster in _TOXIC_CLUSTERS:
        if any(t in low for t in cluster):
            hits += 1
    return hits


def _thin_score(tokens: int, links: int) -> float:
    # Very short pages and pages that are mostly links are spammy.
    s = 0.0
    if tokens < 150:
        s += 0.5
    elif tokens < 300:
        s += 0.2
    if links > 40:
        s += 0.4
    elif links > 15:
        s += 0.2
    return min(1.0, s)


def analyze_poisoning(docs, config) -> Dict:
    """Score every source + entity exposure for vector-poisoning risk."""
    results: List[Dict] = []
    entity_exposure = defaultdict(lambda: {"toxic_sources": 0, "toxic_mentions": 0,
                                           "total_sources": 0})
    for doc in docs:
        text = (doc.text or "").lower()
        tokens = max(1, len(doc.text.split()))
        links = _link_count(doc.raw_html)
        toxic = _toxic_hits(doc.text)

        thin = _thin_score(tokens, links)
        spam_terms = sum(1 for w in _LINK_WORDS if w in text)
        link_ratio = min(1.0, links / max(1, tokens))

        risk = 0.0
        reasons: List[str] = []
        if toxic:
            risk += 0.4
            reasons.append(f"{toxic} toxic-concept cluster(s) co-cited")
        if thin >= 0.4:
            risk += thin
            reasons.append(f"thin content (~{tokens} tokens)")
        if spam_terms >= 3:
            risk += 0.3
            reasons.append(f"{spam_terms} link-bait phrases")
        if link_ratio > 0.10:
            risk += 0.2
            reasons.append(f"high link density ({link_ratio:.0%} of tokens)")

        risk = round(min(1.0, risk), 3)
        is_spam = risk >= 0.5

        # Which focus entities are co-cited on this (potentially toxic) page?
        from ..nlp.ner import NER
        patterns, alias_to_entity = NER.build_mention_patterns(
            config.all_entities(), config.entity_alias_map())
        counts = NER.find_mentions(doc.text, patterns, alias_to_entity)
        entities_present = [e for e, c in counts.items() if c > 0]

        for ent in entities_present:
            entity_exposure[ent]["total_sources"] += 1
            if is_spam:
                entity_exposure[ent]["toxic_sources"] += 1
                entity_exposure[ent]["toxic_mentions"] += counts[ent]

        results.append({
            "url": doc.url,
            "title": doc.title,
            "domain": doc.domain,
            "source_type": doc.source_type,
            "tokens": tokens,
            "outbound_links": links,
            "toxic_cluster_hits": toxic,
            "link_ratio": round(link_ratio, 4),
            "thin_score": round(thin, 3),
            "poisoning_risk": risk,
            "is_spam": is_spam,
            "risk_factors": "; ".join(reasons),
            "entities_co_cited": entities_present,
        })

    results.sort(key=lambda r: r["poisoning_risk"], reverse=True)

    brand = config.target_brand
    exposure = []
    for ent in config.all_entities():
        e = entity_exposure[ent]
        total = e["total_sources"]
        toxic = e["toxic_sources"]
        exposure.append({
            "entity": ent,
            "sources_co_cited": total,
            "toxic_sources": toxic,
            "toxic_share_pct": round(toxic / total * 100.0, 1) if total else 0.0,
            "flags": e["toxic_mentions"],
        })

    brand_exposure = next((x for x in exposure if x["entity"] == brand), None)
    status = "clean"
    if brand_exposure and brand_exposure["toxic_share_pct"] >= 20:
        status = "at-risk"
    if brand_exposure and brand_exposure["toxic_share_pct"] >= 40:
        status = "compromised"

    return {
        "sources": [r for r in results if r["is_spam"]][: config.top_n_recommendations * 2],
        "entity_exposure": exposure,
        "brand_poisoning_status": status,
        "toxic_source_count": sum(1 for r in results if r["is_spam"]),
        "total_sources": len(results),
        "method": "thin-content + toxic-co-citation + link-density heuristic",
    }
