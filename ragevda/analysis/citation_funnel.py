"""Citation-source analytics: cited-vs-found funnel + fan-out decomposition.

Closes the Profound Conversation Explorer / Ahrefs PAA fan-out gap:

* **Funnel**: found_docs -> mention_docs -> cited_docs -> linked_docs per
  entity, with conversion rates. Built from provenance + citation ledger.
* **Fan-out decomposition**: per-topic which query expansions produced the
  citing docs (raw topic vs intent template vs reddit vs competitor-tail),
  so teams see WHERE citations come from.
* **Unlinked authority finder output**: top domains that mention the brand
  without linking (outreach list with contact-page guesses).
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List
from urllib.parse import urlparse


def _domain(url: str) -> str:
    try:
        return (urlparse(url or "").netloc or "").lower().lstrip("www.")
    except Exception:  # noqa: BLE001
        return ""


def citation_funnel(report: Dict, config) -> Dict:
    prov: List[Dict] = report.get("provenance", []) or []
    cit = report.get("citation_gap", {}) or {}
    citations: List[Dict] = cit.get("citations", []) or []
    unlinked: List[Dict] = cit.get("unlinked", []) or cit.get("unlinked_authorities", []) or []
    brand = config.target_brand
    entities = [brand] + list(config.competitor_entities or [])

    found = len(prov)
    funnel = []
    for e in entities:
        el = e.lower()
        mention_docs = sum(1 for p in prov
                           if el in str(p.get("title", "")).lower()
                           or el in str(p.get("url", "")).lower())
        cited = sum(1 for c in citations if str(c.get("entity", "")).lower() == el)
        linked = sum(1 for c in citations
                     if str(c.get("entity", "")).lower() == el
                     and str(c.get("status", "")).lower() in ("linked", "cited"))
        funnel.append({
            "entity": e, "found_docs": found, "mention_docs": mention_docs,
            "cited_docs": cited, "linked_docs": linked,
            "mention_rate_pct": round(100.0 * mention_docs / found, 1) if found else 0.0,
            "cite_rate_pct": round(100.0 * cited / max(1, mention_docs), 1),
            "link_rate_pct": round(100.0 * linked / max(1, cited), 1),
        })

    # fan-out decomposition: classify citing doc by query-expansion family
    fam = Counter()
    for p in prov:
        q = str(p.get("top_topic", "") or "")
        title = str(p.get("title", "") or "").lower()
        if "reddit" in title or "reddit" in str(p.get("url", "")).lower():
            fam["ugc-reddit"] += 1
        elif any(k in title for k in ("news", "breaking")):
            fam["news"] += 1
        elif q and q in title:
            fam["raw-topic"] += 1
        else:
            fam["intent/competitor-tail"] += 1
    total = sum(fam.values()) or 1
    decomposition = [{"family": k, "docs": v,
                      "share_pct": round(100.0 * v / total, 1)}
                     for k, v in fam.most_common()]

    # outreach: top unlinked domains with contact-page guesses
    dom_count = Counter(_domain(u.get("url", "")) for u in unlinked if u.get("url"))
    outreach = [{"domain": d, "unlinked_mentions": n,
                 "contact_guess": f"https://{d}/contact"}
                for d, n in dom_count.most_common(15) if d]
    return {"funnel": funnel, "fanout_decomposition": decomposition,
            "outreach_targets": outreach,
            "method": "funnel from provenance+citation ledger; families from title/URL signals"}
