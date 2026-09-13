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
    out), no body substance after cleaning;
  * machine-generated repetition: unusually high n-gram self-repetition /
    keyword stuffing that betrays a doorway or AI-generated link farm.

The output is a risk-ranked list plus per-entity poisoning exposure, so a team
can disavow / disassociate before it surfaces in AI answers.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
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
    {"crypto", "bitcoin", "airdrop", "defi", "mint-nft", "token-presale"},
]
_LINK_WORDS = {"click here", "read more", "check this out", "visit website",
               "buy now", "order now", "limited offer", "act now",
               "discount code", "free trial now", "apply today"}

# Phrases that indicate machine-generated doorway / boilerplate content rather
# than genuine editorial substance.
_GENERATED_PHRASES = [
    "in conclusion", "to summarize", "in the fast-paced world", "in today's",
    "if you're looking for", "you might be wondering", "it's important to note",
    "in this article, we will explore", "remember to always", "overall, the",
    "whether you're a beginner or an expert",
]

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


def _generated_phrase_hits(text: str) -> int:
    low = text.lower()
    return sum(1 for p in _GENERATED_PHRASES if p in low)


def _repetition_ratio(tokens: List[str]) -> float:
    """Fraud / doorway pages tend to repeat the same handful of keyword phrases.
    Returns a 0..1 score for how repetitively a page uses its own vocabulary,
    measured by the fraction of tokens that are repeats of a top repeated word.
    """
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    total = len(tokens)
    # sum of all tokens minus the count of distinct words => repeated mass
    repeated = sum(cnt for word, cnt in counts.items()
                   if cnt > 1 and len(word) > 3)
    # penalise top-heavy repetition more strongly
    top = counts.most_common(1)[0][1]
    return min(1.0, ( (repeated / total) * 0.6 ) + ( (top / total) * 0.4 ))


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


def _machine_score(generated: int, repetition: float) -> float:
    """Combine generated-phrase and repetition signals into a machine-quality
    score (higher = more likely a machine-generated doorway page)."""
    s = 0.0
    if generated >= 3:
        s += 0.5
    elif generated >= 1:
        s += 0.25
    s += repetition * 0.5
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

        word_tokens = re.findall(r"[a-z']+", text)
        repetition = _repetition_ratio(word_tokens)
        generated = _generated_phrase_hits(doc.text)
        machine = _machine_score(generated, repetition)

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
        if machine >= 0.4:
            risk += machine * 0.3
            reasons.append(
                f"machine-generated pattern (rep {repetition:.2f}, "
                f"{generated} boilerplate phrase(s))")

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
            "repetition_score": round(repetition, 3),
            "generated_phrase_hits": generated,
            "machine_score": round(machine, 3),
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

    # Brand-level machine-content signal: mean repetition/machine score across
    # every source that co-cites the brand (not just the flagged/spam ones), so
    # the brief can see whether the brand's co-citation neighbourhood skews
    # toward programmatic doorway pages even before they trip the spam bar.
    brand_machine_vals: List[float] = []
    brand_rep_vals: List[float] = []
    brand_generated_hits = 0
    for s in results:
        if brand in s["entities_co_cited"]:
            brand_machine_vals.append(s["machine_score"])
            brand_rep_vals.append(s["repetition_score"])
            brand_generated_hits += s["generated_phrase_hits"]
    brand_machine_agg = round(
        (sum(brand_machine_vals) / len(brand_machine_vals)) if brand_machine_vals else 0.0, 3)
    brand_rep_agg = round(
        (sum(brand_rep_vals) / len(brand_rep_vals)) if brand_rep_vals else 0.0, 3)

    return {
        "sources": [r for r in results if r["is_spam"]][: config.top_n_recommendations * 2],
        "entity_exposure": exposure,
        "brand_poisoning_status": status,
        "toxic_source_count": sum(1 for r in results if r["is_spam"]),
        "total_sources": len(results),
        "brand_machine_score": brand_machine_agg,
        "brand_repetition_score": brand_rep_agg,
        "brand_generated_phrase_hits": brand_generated_hits,
        "verified": False,
        "estimate": True,
        "method": ("HEURISTIC TRIAGE ESTIMATE — thin-content + toxic-co-citation + "
                   "link-density + machine-generated-repetition heuristics. "
                   "Use only for manual review prioritisation, never as an ML "
                   "probability or verified penalty."),
    }
