"""Standalone sub-process fetcher used by auto_probe.

A direct in-process fetch can wedge an entire server when a host stalls the
very first connection at the TLS/socket layer (AV scanning, hostile networks)
in a way that outlives even httpx's own timeouts.  This helper runs fetch-only
in its own Python process so the parent can always kill it with a hard timeout
via ``subprocess.run(..., timeout=...)``.

Uses httpx (installed in the venv) rather than urllib: empirically urllib's
URL opener stalls on this machine while httpx completes the same request in a
second.  The parent passes the User-Agent via RAGEVDA_UA so nothing from the
repo has to be importable here.
"""

import json
import os
import re
import sys

MAX_HTML = 400_000


def _meta_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return m.group(1).strip() if m else ""


def _extract_meta(html: str) -> dict:
    meta = {}
    for key in ("description", "keywords", "og:title", "og:description",
                "og:site_name", "author"):
        pat = (r'<meta[^>]+(?:name|property)=["\']' + re.escape(key) +
               r'["\'][^>]+content=["\'](.*?)["\']')
        alt = (r'<meta[^>]+content=["\'](.*?)["\'][^>]+(?:name|property)=["\']'
               + re.escape(key) + r'["\']')
        m = re.search(pat, html, re.I | re.S) or re.search(alt, html, re.I | re.S)
        if m:
            meta[key] = m.group(1).strip()
    return meta


def _fetch(url: str) -> dict:
    import httpx

    headers = {
        "User-Agent": os.environ.get(
            "RAGEVDA_UA",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        ),
        "Accept-Language": "en",
        "Accept": "text/html,application/xhtml+xml",
    }
    with httpx.Client(timeout=7, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        if resp.status_code != 200:
            return {}
        html = resp.text
    if len(html) > MAX_HTML:
        html = html[:MAX_HTML]
    return {
        "title": _meta_title(html),
        "html": html,
        "final_url": str(resp.url),
        "meta": _extract_meta(html),
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("{}")
        return
    try:
        print(json.dumps(_fetch(sys.argv[1])))
    except Exception:  # noqa: BLE001 — best effort; parent treats {} as None
        print("{}")


if __name__ == "__main__":
    main()