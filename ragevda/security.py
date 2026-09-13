"""Web/API security: API-key auth, rate limiting, CSRF.

* API keys: ``RAGEVDA_API_KEY`` env or ``config.api_key``; constant-time compare.
* Rate limit: in-memory token bucket per IP (60 req/min default).
* CSRF: double-submit cookie — POST /run requires X-CSRF-Token == csrf cookie.
Fail-open ONLY when no API key is configured (local single-user mode); when a
key IS configured, missing/wrong keys get 401 (no breach-by-default).
"""
from __future__ import annotations

import hmac
import os
import secrets
import time
from collections import defaultdict
from typing import Dict, List

_BUCKETS: Dict[str, List[float]] = defaultdict(list)
_WINDOW = 60.0
_LIMIT = 60


def api_key_configured(config_key: str = "") -> bool:
    return bool(config_key or os.environ.get("RAGEVDA_API_KEY", ""))


def check_api_key(provided: str = "", config_key: str = "") -> bool:
    expected = config_key or os.environ.get("RAGEVDA_API_KEY", "")
    if not expected:
        return True  # local single-user mode: no key required
    return hmac.compare_digest(str(provided or ""), expected)


def rate_limited(ip: str, limit: int = _LIMIT) -> bool:
    now = time.time()
    b = _BUCKETS[ip]
    _BUCKETS[ip] = [t for t in b if now - t < _WINDOW]
    if len(_BUCKETS[ip]) >= limit:
        return True
    _BUCKETS[ip].append(now)
    return False


def new_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def check_csrf(cookie_token: str = "", header_token: str = "") -> bool:
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)


def bind_address(configured: str = "") -> str:
    """Default to loopback. 0.0.0.0 only when explicitly requested."""
    if configured:
        return configured
    if os.environ.get("RAGEVDA_BIND", ""):
        return os.environ["RAGEVDA_BIND"]
    return "127.0.0.1"
