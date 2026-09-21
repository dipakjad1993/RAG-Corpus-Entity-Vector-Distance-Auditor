"""Real robots.txt enforcement helper (P2 trust).

The harvester is concurrency-capped and polite, but politeness without
checking robots.txt is a claim, not a control. This module provides a tiny
fail-open wrapper around ``urllib.robotparser``:

* ``allowed(url, user_agent)`` -> True/False (True on any error: fail-open,
  never blocks an audit on a robots-fetch failure).
* ``filter_urls(urls, ...)`` -> (allowed, blocked) split for logging.

No new dependencies (stdlib only). Wire into fetch paths incrementally;
the web UI + CLI log blocked counts so politeness is auditable.
"""
from __future__ import annotations

import functools
import urllib.parse
import urllib.robotparser
from typing import Iterable, List, Tuple


@functools.lru_cache(maxsize=256)
def _parser_for(origin: str) -> urllib.robotparser.RobotFileParser | None:
    try:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(origin.rstrip("/") + "/robots.txt")
        rp.read()  # network read; short default timeout inside robotparser
        return rp
    except Exception:
        return None


def allowed(url: str, user_agent: str = "RAG-EVDA") -> bool:
    """True if fetching ``url`` is allowed by the host robots.txt.

    Fail-open: unparseable URL, missing robots.txt, or fetch error -> True
    (audit continues; the decision is logged by the caller).
    """
    try:
        parts = urllib.parse.urlsplit(url)
        if not parts.scheme.startswith("http") or not parts.netloc:
            return True
        origin = f"{parts.scheme}://{parts.netloc}"
        rp = _parser_for(origin)
        if rp is None:
            return True
        return bool(rp.can_fetch(user_agent or "*", url))
    except Exception:
        return True


def filter_urls(urls: Iterable[str], user_agent: str = "RAG-EVDA") -> Tuple[List[str], List[str]]:
    ok: List[str] = []
    blocked: List[str] = []
    for u in urls or []:
        (ok if allowed(str(u), user_agent) else blocked).append(str(u))
    return ok, blocked
