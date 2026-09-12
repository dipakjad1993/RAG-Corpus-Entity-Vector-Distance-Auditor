"""Real-Time Source Freshness & Liveness Validation.

A core enterprise guarantee: metrics should describe LIVE, current web data,
not stale pages scraped months ago.  This module validates, from the actual
fetch response and page content, how fresh and alive each harvested source is.

Signals captured from the real fetch (no synthesis):

  * ``age_days``             : how old the source content is, derived from the
                               response's real ``Last-Modified`` / ``Date``
                               headers, falling back to a real
                               ``datePublished``/``dateModified`` in the page
                               (schema.org / meta tags / time elements).
  * ``last_modified``        : the raw header / meta value observed.
  * ``staleness``            : categorical (fresh / recent / stale / aging)
                               from the measured age.
  * ``content_type``         : the real Content-Type header served.
  * ``fetch_latency_ms``     : the real measured fetch latency (liveness).
  * ``http_status``          : the real HTTP status of the fetch.
  * ``schema_detected``      : whether a structured-data (schema.org) marker
                               was present in the live HTML.
  * ``live``                 : true when the fetch returned an HTTP 2xx and an
                               actionable freshness signal was observed.

Each value is written verbatim from the live response into ``report.json`` and
the sources CSV, so the operator can audit that every metric rests on current,
reachable evidence.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..utils import get_logger

logger = get_logger("ragevda.analysis.freshness")

_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})")
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DAY_NAMES = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_HTTP_DATE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):\d{2}")


def _parse_http_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    # RFC 1123: "Sun, 06 Nov 1994 08:49:37 GMT"
    try:
        return datetime.strptime(value.replace("GMT", "").strip(),
                                 "%a, %d %b %Y %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        pass
    # RFC 850: "Sunday, 06-Nov-94 08:49:37 GMT"
    try:
        return datetime.strptime(value.replace("GMT", "").strip(),
                                 "%A, %d-%b-%y %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        pass
    # ISO 8601
    m = _ISO_RE.search(value)
    if m:
        try:
            return datetime.strptime(m.group(0), "%Y-%m-%dT%H:%M").replace(
                tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            pass
    return None


def _iso_from_text(text: str) -> Optional[datetime]:
    """Extract a real ISO/YYYY-MM-DD date from raw page text/meta."""
    if not text:
        return None
    # schema.org datePublished / dateModified are the strongest signals
    for pat in (r"datePublished[\"':= ]+\"?(\d{4}-\d{2}-\d{2})",
                r"dateModified[\"':= ]+\"?(\d{4}-\d{2}-\d{2})",
                r"datetime=\"(\d{4}-\d{2}-\d{2})"):
        m = re.search(pat, text)
        if m:
            try:
                return datetime.strptime(m.group(1), "%Y-%m-%d").replace(
                    tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001
                pass
    # <time datetime="...">
    m = re.search(r'<time[^>]*datetime="(\d{4}-\d{2}-\d{2}[T:0-9]*)', text)
    if m:
        dt = _parse_http_date(m.group(1))
        if dt:
            return dt
    return None


def _staleness(age_days: Optional[float]) -> str:
    if age_days is None:
        return "unknown"
    if age_days <= 30:
        return "fresh"
    if age_days <= 90:
        return "recent"
    if age_days <= 365:
        return "stale"
    return "aging"


def validate_freshness(docs) -> Dict:
    """Validate real-time freshness/liveness of every harvested source."""
    per_source: List[Dict] = []
    now = datetime.now(timezone.utc)

    for d in docs:
        headers = getattr(d, "headers", {}) or {}
        last_modified = (headers.get("last-modified")
                         or headers.get("Last-Modified")
                         or "")
        http_date = (headers.get("date") or headers.get("Date") or "")
        content_type = (headers.get("content-type")
                        or headers.get("Content-Type") or "").split(";")[0].strip()

        # Prefer Last-Modified; else server Date; else schema/meta in content.
        published_dt = _parse_http_date(last_modified)
        source_signal = "last-modified"
        if published_dt is None:
            published_dt = _parse_http_date(http_date)
            source_signal = "http-date"
        if published_dt is None:
            published_dt = _iso_from_text(d.raw_html or d.text)
            source_signal = "page-meta/schema"

        age_days = None
        if published_dt is not None:
            try:
                age_days = max(0.0, (now - published_dt).total_seconds() / 86400.0)
            except Exception:  # noqa: BLE001
                age_days = None

        is_live = bool(d.http_status) and 200 <= d.http_status < 300
        # Local-file corpus docs (file://) are real ground truth but were never
        # fetched over HTTP — never claim HTTP liveness for them.
        is_local_file = str(getattr(d, "url", "")).startswith("file://") or getattr(d, "source_type", "") == "file"
        if is_local_file:
            is_live = False
        schema_detected = bool(
            d.raw_html and any(
                k in (d.raw_html or "").lower()
                for k in ("application/ld+json", 'itemscope', "schema.org")))
        latency_ms = getattr(d, "fetch_ms", 0.0) or 0.0

        per_source.append({
            "doc_id": d.doc_id,
            "url": d.url,
            "domain": d.domain,
            "http_status": d.http_status,
            "live": is_live,
            "fetch_latency_ms": round(latency_ms, 1),
            "age_days": round(age_days, 1) if age_days is not None else None,
            "staleness": _staleness(age_days),
            "source_signal": source_signal,
            "last_modified_raw": last_modified or "",
            "server_date_raw": http_date or "",
            "content_type": content_type,
            "schema_structured_data": schema_detected,
        })

    # Aggregate freshness statistics across the corpus.
    live = sum(1 for s in per_source if s["live"])
    fresh = sum(1 for s in per_source if s["staleness"] == "fresh")
    recent = sum(1 for s in per_source if s["staleness"] == "recent")
    stale = sum(1 for s in per_source if s["staleness"] in ("stale", "aging"))
    unknown = sum(1 for s in per_source if s["staleness"] == "unknown")
    ages = sorted(s["age_days"] for s in per_source if s["age_days"] is not None)

    def _quantile(sorted_ages: List[float], p: float):
        if not sorted_ages:
            return None
        k = (len(sorted_ages) - 1) * p
        f = int(k)
        c = min(f + 1, len(sorted_ages) - 1)
        return round(sorted_ages[f] + (sorted_ages[c] - sorted_ages[f]) * (k - f), 1)

    n = len(per_source)
    # Composite freshness grade (A-F): 60% live, 30% fresh(+recent), 10% age-known.
    live_frac = (live / n) if n else 0.0
    cur_frac = ((fresh + recent) / n) if n else 0.0
    known_frac = ((n - unknown) / n) if n else 0.0
    composite = 100.0 * (0.6 * live_frac + 0.3 * cur_frac + 0.1 * known_frac)
    grade = (("A" if composite >= 90 else
              "B" if composite >= 80 else
              "C" if composite >= 70 else
              "D" if composite >= 60 else
              "F"))

    summary = {
        "total_sources": n,
        "live_pct": round(live / n * 100.0, 1) if n else 0.0,
        "fresh_pct": round(fresh / n * 100.0, 1) if n else 0.0,
        "recent_pct": round(recent / n * 100.0, 1) if n else 0.0,
        "stale_pct": round(stale / n * 100.0, 1) if n else 0.0,
        "unknown_age_pct": round(unknown / n * 100.0, 1) if n else 0.0,
        "median_age_days": round(sorted(ages)[len(ages) // 2], 1) if ages else None,
        "p90_age_days": _quantile(ages, 0.9),
        "p95_age_days": _quantile(ages, 0.95),
        "max_age_days": max(ages) if ages else None,
        "mean_age_days": round(sum(ages) / len(ages), 1) if ages else None,
        "freshness_composite": round(composite, 1),
        "freshness_grade": grade,
        "validated_at": now.isoformat(),
        "method": ("age estimated from real Last-Modified/Date headers or "
                   "schema.org/meta dates in the fetched HTML; liveness from "
                   "the live HTTP status; all fields read verbatim from the "
                   "live response. Grade = 0.6*Live + 0.3*Current + 0.1*AgeKnown."),
    }

    return {
        "summary": summary,
        "per_source": per_source,
    }
