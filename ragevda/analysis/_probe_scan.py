"""Standalone sub-process scanner used by auto_probe for *secondary* pages.

While the primary homepage fetch runs in its own short-lived process (see
``_probe_fetch.py``), this helper fetches a handful of discovery endpoints in
parallel inside ONE throwaway process so the parent can hard-timeout the whole
bundle:  robots.txt, sitemap.xml, about/products/contact pages, feed URLs.

Everything is best-effort: any URL that fails or stalls is dropped and only
what actually came back (status 200, small bodies) is returned as JSON so the
probe never depends on a single flaky endpoint.

Interface: ``python _probe_scan.py <json-url-list>`` -> ``{"<url>": {...}}``
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_HTML = 250_000
REQUEST_TIMEOUT = 4.5
MAX_CONCURRENCY = 6


def _extract_meta(html: str) -> dict:
    meta = {}
    for key in ("description", "keywords", "og:title", "og:description",
                "og:site_name", "og:locale", "author"):
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
        "Accept": "*/*",
    }
    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True,
                      headers=headers) as client:
        resp = client.get(url)
        if resp.status_code != 200:
            return {}
        html = resp.text
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if m:
        title = m.group(1).strip()
    if len(html) > MAX_HTML:
        html = html[:MAX_HTML]
    return {
        "title": title,
        "html": html,
        "final_url": str(resp.url),
        "meta": _extract_meta(html),
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("{}")
        sys.stdout.flush()
        os._exit(0)
    try:
        urls = json.loads(sys.argv[1])
    except Exception:  # noqa: BLE001
        print("{}")
        sys.stdout.flush()
        os._exit(0)
    urls = [u for u in urls if isinstance(u, str) and u.startswith("http")][:10]
    out: dict = {}
    if not urls:
        print("{}")
        sys.stdout.flush()
        os._exit(0)
    pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY)
    futs = {pool.submit(_fetch, u): u for u in urls}
    # Never fail the whole bundle because one endpoint stalls (DNS on
    # Windows can hang longer than any httpx timeout).  Collect what
    # completed, drop the stragglers, and hand the JSON back.
    try:
        for fut in as_completed(futs, timeout=min(6.0, REQUEST_TIMEOUT * 1.5 + 1)):
            url = futs[fut]
            try:
                data = fut.result()
            except Exception:  # noqa: BLE001
                data = {}
            if data:
                out[url] = data
    except TimeoutError:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:  # noqa: BLE001
        pool.shutdown(wait=False, cancel_futures=True)
    print(json.dumps(out))
    sys.stdout.flush()
    # hard-exit so an unstarted thread / hanging DNS lookup cannot keep the
    # interpreter alive and blow the parent's subprocess budget
    os._exit(0)


if __name__ == "__main__":
    main()