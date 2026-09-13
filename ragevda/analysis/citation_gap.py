"""Feature D + RAG Invisibility Index: link vs. mention auditing.

For every retrieved document we classify each target entity as:

* ``linked``     -> the entity appears as the *text of an anchor* (<a>..</a>)
* ``unlinked``   -> the entity appears in body text but never as a link
* ``omitted``    -> the entity does not appear at all

From this we derive:
* per-entity linked / unlinked / omitted document counts
* the **RAG Invisibility Index** -- the share of high-relevance industry
  articles where the brand is completely absent while at least one competitor
  is cited
* the **High-Density Off-Page Target List** -- URLs that are highly relevant
  to a target topic but do not yet mention the brand.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .context import AnalysisContext
from ..nlp.ner import NER
from ..utils import get_logger

logger = get_logger("ragevda.analysis.citation_gap")


@dataclass
class DocCitation:
    doc_id: str
    url: str
    title: str
    source_type: str
    linked: Set[str]
    unlinked: Set[str]
    omitted: Set[str]
    max_topic: str
    max_topic_sim: float


def _linked_entities(raw_html: str, patterns: Dict[str, re.Pattern],
                     alias_to_entity: Optional[Dict[str, str]] = None,
                     domain_map: Optional[Dict[str, List[str]]] = None
                     ) -> Set[str]:
    """Entities that appear as anchor text (or as a link to the entity's own
    domain) in the HTML. Returns ORIGINAL-case entity strings (aliases and
    domain links are remapped via ``alias_to_entity`` / ``domain_map``)."""
    found: Set[str] = set()
    if not raw_html:
        return found
    alias_to_entity = alias_to_entity or {}
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, "lxml")
        for a in soup.find_all("a"):
            txt = a.get_text(" ", strip=True)
            href = (a.get("href") or "").lower()
            for key, pat in patterns.items():
                if key and pat.search(txt):
                    found.add(alias_to_entity.get(key, key))
            if domain_map:
                for ent, doms in domain_map.items():
                    el = ent.lower()
                    if any(d and (href == d or href.endswith("." + d)
                                  or ("/" + d) in href) for d in doms):
                        found.add(ent)
    except Exception as exc:  # noqa: BLE001
        logger.debug("linked-entity parse skipped: %s", exc)
    return found


def analyze_citation_gap(ctx: AnalysisContext) -> Dict:
    cfg = ctx.config
    focus = cfg.all_entities()
    alias_map = cfg.entity_alias_map()
    domain_map = cfg.entity_domain_map()
    patterns, alias_to_entity = NER.build_mention_patterns(focus, alias_map)
    brand = cfg.target_brand.lower()

    citations: List[DocCitation] = []
    entity_linked: Counter = Counter()
    entity_unlinked: Counter = Counter()
    entity_omitted: Counter = Counter()

    high_rel_docs = 0
    invis_docs = 0  # brand omitted + >=1 competitor present, high relevance

    target_list: List[Dict] = []

    for doc in ctx.docs:
        # Linked = entity appears as anchor text OR as a link to its own domain.
        linked = {e.lower() for e in
                  _linked_entities(doc.raw_html, patterns, alias_to_entity, domain_map)}
        # Mentioned = exact/alias substring match in the body text ...
        counts = NER.find_mentions(doc.text, patterns, alias_to_entity)
        mentioned_text = {e.lower() for e in counts if counts[e] > 0}
        # ... PLUS domain-based presence: a page on the brand's own domain is a
        # genuine mention even if the literal name never appears in the text.
        d = (doc.domain or "").lower()
        if d:
            for ent in focus:
                el = ent.lower()
                for dm in domain_map.get(ent, []):
                    if d == dm or d.endswith("." + dm):
                        mentioned_text.add(el)
                        break

        unlinked = mentioned_text - linked
        omitted = {f.lower() for f in focus} - (mentioned_text | linked)

        for e in linked:
            entity_linked[e] += 1
        for e in unlinked:
            entity_unlinked[e] += 1
        for e in omitted:
            entity_omitted[e] += 1

        # most relevant topic for this doc
        per_topic = ctx.doc_topic_max_sim.get(doc.doc_id, {})
        max_topic = max(per_topic, key=per_topic.get) if per_topic else ""
        max_sim = per_topic.get(max_topic, 0.0)

        citations.append(DocCitation(
            doc_id=doc.doc_id, url=doc.url, title=doc.title,
            source_type=doc.source_type, linked=linked, unlinked=unlinked,
            omitted=omitted, max_topic=max_topic, max_topic_sim=max_sim,
        ))

        brand_omitted = brand in omitted
        competitor_present = any(c.lower() in (linked | unlinked) for c in cfg.competitor_entities)
        thr = ctx.topic_thresholds.get(max_topic, cfg.high_relevance_threshold) if max_topic else cfg.high_relevance_threshold
        high_relevance = max_sim >= thr

        if high_relevance:
            high_rel_docs += 1

        # RAG Invisibility Index is measured across the harvested corpus
        # (these ARE the high-ranking articles). A doc counts as "invisible"
        # when the brand is absent while at least one competitor is cited.
        if brand_omitted and competitor_present:
            invis_docs += 1

        # Off-page target: brand omitted -> candidate for outreach.
        # We keep every such doc (ranked by relevance) so the list is never
        # empty due to absolute-threshold calibration, and flag the ones that
        # clear the high-relevance bar separately.
        if brand_omitted:
            target_list.append({
                "url": doc.url,
                "title": doc.title,
                "source_type": doc.source_type,
                "top_topic": max_topic,
                "topic_relevance": round(max_sim, 4),
                "high_relevance": high_relevance,
                "competitors_present": sorted(
                    c for c in cfg.competitor_entities
                    if c.lower() in (linked | unlinked)
                ),
                "competitor_links": sorted(
                    c for c in cfg.competitor_entities if c.lower() in linked
                ),
            })

    total_docs = len(ctx.docs)
    # Denominator = harvested high-ranking corpus size.
    invisibility_index = round(
        (invis_docs / total_docs * 100.0) if total_docs else 0.0, 2
    )

    # Per-entity summary
    entity_summary = []
    for ent in focus:
        elow = ent.lower()
        linked_n = entity_linked.get(elow, 0)
        unlinked_n = entity_unlinked.get(elow, 0)
        omitted_n = entity_omitted.get(elow, 0)
        mentioned_n = linked_n + unlinked_n
        total = len(ctx.docs)
        link_rate = round(linked_n / mentioned_n * 100.0, 1) if mentioned_n else 0.0
        entity_summary.append({
            "entity": ent,
            "docs_total": total,
            "docs_mentioned": mentioned_n,
            "docs_linked": linked_n,
            "docs_unlinked": unlinked_n,
            "docs_omitted": omitted_n,
            "mention_rate_pct": round(mentioned_n / total * 100.0, 1) if total else 0.0,
            "link_rate_of_mentions_pct": link_rate,
        })

    # Rank off-page targets
    target_list.sort(
        key=lambda r: (r["high_relevance"], r["topic_relevance"],
                      len(r["competitors_present"])),
        reverse=True,
    )
    target_list = target_list[: cfg.top_n_recommendations * 2]

    ghost = compute_ghost_citations(ctx, citations)
    ingain = information_gain(ctx)

    return {
        "entity_summary": entity_summary,
        "rag_invisibility_index": invisibility_index,
        "high_relevance_doc_count": high_rel_docs,
        "invisible_doc_count": invis_docs,
        "off_page_targets": target_list,
        "citations": citations,
        "ghost_citations": ghost,
        "information_gain": ingain,
    }


def compute_ghost_citations(ctx: AnalysisContext, citations: List[DocCitation]) -> Dict:
    """E-E-A-T ghost citations: 73% of mentions don't name the brand.

    A ghost citation = doc is highly relevant to a topic AND links/cites the
    brand's domain (or answer-engine cited_urls include it) WITHOUT naming the
    brand in text. Tracked per doc with evidence (no synthesis).
    """
    ghost_docs: List[Dict] = []
    brand = ctx.config.target_brand.lower()
    for c in citations:
        if brand not in c.omitted:
            continue  # named => not a ghost
        doc = ctx.doc_by_id.get(c.doc_id) if hasattr(ctx, "doc_by_id") else None
        if doc is None:
            continue
        html = (getattr(doc, "raw_html", "") or "").lower()
        doms = [d.lower() for d in (ctx.config.entity_domain_map().get(ctx.config.target_brand, []) or [])]
        domain_hit = any(d and d in html for d in doms)
        cited = ((getattr(doc, "metadata", {}) or {}).get("cited_urls", []) or [])
        cited_hit = any(any(d and d in (u or "").lower() for d in doms) for u in cited)
        per = ctx.doc_topic_max_sim.get(c.doc_id, {})
        top = max(per, key=per.get) if per else ""
        if (domain_hit or cited_hit) and top:
            ghost_docs.append({"doc_id": c.doc_id, "url": c.url, "topic": top,
                               "evidence": "domain-link-without-name" if domain_hit else "answer-cited-without-name"})
    return {"ghost_count": len(ghost_docs), "ghost_docs": ghost_docs[:50],
            "method": "domain/citation present but brand unnamed in high-relevance docs"}


def information_gain(ctx: AnalysisContext) -> Dict:
    """Information Gain scoring: original research (86.7) > structured data (75.8).

    Scores each doc 0-100 from real signals: token length (depth), schema.org
    presence, tables/lists, quotes/stats, outbound citations. Brand's mean vs
    competitor mean exposes the originality gap.
    """
    import re as _re
    brand = ctx.config.target_brand
    docs = ctx.docs
    patterns, alias = NER.build_mention_patterns(
        ctx.config.all_entities(), ctx.config.entity_alias_map())
    scores = {}
    for doc in docs:
        html = (doc.raw_html or "").lower()
        text = doc.text or ""
        s = 0.0
        s += min(30.0, len(text) / 1000.0)                       # depth (30)
        if "application/ld+json" in html or "schema.org" in html:
            s += 15.0                                            # structured (15)
        s += min(15.0, 3.0 * len(_re.findall(r"<table|<ul|<ol", html)))  # data (15)
        s += min(20.0, 2.0 * len(_re.findall(r"\d+(?:\.\d+)?%", text)))  # stats (20)
        s += min(20.0, 2.0 * len(_re.findall(r"https?://", html)))      # cites (20)
        scores[doc.doc_id] = round(min(100.0, s), 1)
    def _mean(ids):
        vals = [scores[i] for i in ids if i in scores]
        return round(sum(vals) / len(vals), 1) if vals else 0.0
    brand_ids = [d.doc_id for d in docs
                 if NER.find_mentions(d.text, patterns, alias).get(brand, 0) > 0]
    return {"per_doc": scores, "brand_mean": _mean(brand_ids),
            "corpus_mean": _mean(list(scores)),
            "method": "depth 30 + structured 15 + data-tables 15 + stats 20 + citations 20"}
