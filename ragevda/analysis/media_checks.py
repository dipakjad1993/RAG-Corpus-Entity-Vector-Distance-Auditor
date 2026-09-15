"""Image / video / Merchant / GBP checks (Google 2026: non-text citations).

Harvests og:image / video signals from fetched HTML (stored on doc when the
cleaner preserves meta) plus YouTube chapter presence in UGC docs. Merchant
Center + Google Business Profile drive product/local AI surfaces — flag when
product/local topics lack them. All evidence from real fetched docs.
"""
from __future__ import annotations

import re
from typing import Dict

_IMG = re.compile(r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)", re.I)
_VID = re.compile(r"(og:video|youtube\.com/watch|youtu\.be/|\"chapters?\"|T0:\d+:\d+)", re.I)
_PRICE = re.compile(r"(price|£|\$|€|in stock|out of stock|availability|Merchant Center)", re.I)
_GBP = re.compile(r"(google business|business profile|opening hours|reviews? on google|directions)", re.I)


def media_checks(docs, topics) -> Dict:
    rows = []
    for d in (docs or []):
        html = getattr(d, "html", "") or ""
        text = (getattr(d, "text", "") or "")[:6000]
        has_img = bool(_IMG.search(html) or getattr(d, "og_image", ""))
        has_vid = bool(_VID.search(html + text) or "youtube" in (getattr(d, "url", "") or ""))
        has_offer = bool(_PRICE.search(text))
        has_gbp = bool(_GBP.search(text))
        rows.append({"url": getattr(d, "url", ""), "title": getattr(d, "title", ""),
                     "has_image": has_img, "has_video": has_vid,
                     "has_offer_signals": has_offer, "has_gbp_signals": has_gbp})
    n = max(1, len(rows))
    summary = {
        "image_pct": round(100 * sum(r["has_image"] for r in rows) / n, 1),
        "video_pct": round(100 * sum(r["has_video"] for r in rows) / n, 1),
        "offer_pct": round(100 * sum(r["has_offer_signals"] for r in rows) / n, 1),
        "gbp_pct": round(100 * sum(r["has_gbp_signals"] for r in rows) / n, 1),
    }
    topics_l = " ".join(topics or []).lower()
    needs = []
    if ("product" in topics_l or "price" in topics_l) and summary["offer_pct"] < 50:
        needs.append("Add Product schema + Merchant Center feed (product AI surfaces need offer/availability).")
    if summary["image_pct"] < 50:
        needs.append("Add og:image + descriptive alt per page (images earn non-text citations).")
    if summary["video_pct"] < 20:
        needs.append("Add a 2-min demo video with chapters on YouTube + embed (video citations).")
    return {"rows": rows[:200], "summary": summary, "recommendations": needs,
            "method": "og:image/og:video/YouTube-chapter + offer/GBP regex on real fetched docs"}
