"""Automatic brand / business probe (deep, field-complete).

When the operator supplies only a brand name OR a business/homepage URL in the
"Target Brand Name" field, this module:

* fetches the live site in a killable sub-process (homepage) plus a parallel
  discovery scan (robots.txt / sitemap.xml / about / products / feeds and local
  SearXNG+Ollama service probes),
* runs budgeted keyless web searches (DDG) for topics, competitors, alternatives,
* reads schema.org JSON-LD, feed links, meta keywords/headings, navigation
  labels, entity phrases, geo/language/currency indicators,
* and derives a default for **every** input field in the web form — brand,
  topics, competitors, crawl depth, locality, harvester, search intent, engine
  matrix, entity weighting + ontology aliases, query templates, SERP footprints,
  content feeds, embedding/spacy models, chunk/density/retrieval knobs and
  relevance thresholds.

Everything is derived from live evidence (the fetched pages + real search
results) and offered as pre-fill; the operator can always edit before running.
Nothing is fabricated: values that genuinely cannot be inferred (e.g. internal
corpus folders) are left out and reported in ``_meta`` so the UI can tell the
user exactly what to fill in by hand.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from ..config import DEFAULT_ENGINE_MATRIX, DEFAULT_USER_AGENT
from ..utils import get_logger

logger = get_logger("ragevda.analysis.probe")

# Total wall-clock budget for the whole probe (fetch + scans + searches).
# Deep-research grade: homepage + discovery scan + multi-query live searches.
_PROBE_BUDGET = 45.0
_HOME_FETCH_BUDGET = 10.0
_SCAN_BUDGET = 12.0


def _run_with_budget(fn, budget: float, *args):
    """Run fn(*args) on a daemon thread and give up after ``budget`` seconds."""
    box: Dict[str, Any] = {"result": None, "done": False}

    def _wrapped():
        try:
            box["result"] = fn(*args)
        except Exception:  # noqa: BLE001
            box["result"] = None
        box["done"] = True

    th = threading.Thread(target=_wrapped, daemon=True)
    th.start()
    th.join(budget)
    return box["result"]


def _subprocess_json(helper: str, arg: str, env: Dict[str, str],
                     budget: float) -> dict:
    """Run a standalone helper subprocess (killable) and parse its JSON."""
    if not os.path.exists(helper):
        return {}
    try:
        proc = subprocess.run(
            [sys.executable, helper, arg],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=budget,
            env=env,
        )
    except Exception:  # noqa: BLE001 — TimeoutExpired, OSError, ...
        return {}
    if proc.returncode != 0:
        return {}
    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except Exception:  # noqa: BLE001
        data = {}
    return data if isinstance(data, dict) else {}


def _fetch_url_safe(url: str, budget: float = _HOME_FETCH_BUDGET
                    ) -> Optional[Dict[str, str]]:
    """Fetch a single URL in a separate process the parent can always kill.

    Returns None on any failure / timeout so callers can fall back to search.
    """
    helper = os.path.join(os.path.dirname(__file__), "_probe_fetch.py")
    env = dict(os.environ)
    env["RAGEVDA_UA"] = DEFAULT_USER_AGENT
    data = _subprocess_json(helper, url, env, budget)
    return data or None


def _fetch_many(urls: List[str], budget: float = _SCAN_BUDGET) -> Dict[str, dict]:
    """Fetch several discovery endpoints in ONE killable sub-process."""
    helper = os.path.join(os.path.dirname(__file__), "_probe_scan.py")
    env = dict(os.environ)
    env["RAGEVDA_UA"] = DEFAULT_USER_AGENT
    return _subprocess_json(helper, json.dumps(urls), env, budget)


def _http_client(timeout: int = 5):
    try:
        import httpx

        return httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept-Language": "en",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("httpx unavailable for probe: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Small text / list helpers
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "and", "or", "for", "with", "your", "our", "their", "this", "that",
    "are", "was", "were", "have", "has", "had", "not", "but", "you", "we",
    "they", "a", "an", "of", "to", "in", "on", "at", "by", "from", "as", "is",
    "be", "will", "can", "more", "most", "best", "top", "about", "what", "how",
    "why", "when", "where", "which", "who", "all", "any", "each", "new", "now",
    "our", "get", "out", "over", "vs", "versus", "&",
}


def _dedupe(seq: List[str], limit: Optional[int] = None) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for item in seq:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        if len(item) < 3:
            continue
        seen.add(key)
        out.append(item)
        if limit and len(out) >= limit:
            break
    return out


def _tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^A-Za-z0-9 .&'-]+", text or "") if t]


def _absolutize(href: str, base: str) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
        return None
    url = urljoin(base, href)
    if url.startswith(("http://", "https://")):
        return url
    return None


def _same_site(url: str, base: str) -> bool:
    u = _domain(url)
    b = _domain(base)
    return bool(u) and u == b


# ---------------------------------------------------------------------------
# DuckDuckGo search (reuses the same keyless client the audit uses)
# ---------------------------------------------------------------------------

def _search(
    query: str,
    depth: int = 8,
    region: str = "wt-wt",
    max_seconds: Optional[float] = 6.0,
) -> List[Dict[str, str]]:
    try:
        from ddgs import DDGS
    except Exception:  # noqa: BLE001
        try:
            from duckduckgo_search import DDGS
        except Exception:  # noqa: BLE001
            return []
    # ddgs 9.x 'auto' aggregates startpage/google/wikipedia/grokipedia etc.,
    # some of which have been refusing connections on this box and silently
    # burning the whole budget.  Individual backends are also flaky here
    # (DDG rate-limits to "No results found."), so we rotate through the
    # independent engines and take the first one that actually answers.
    backends = ("duckduckgo", "yahoo", "mojeek", "brave")
    start = time.monotonic()
    if max_seconds is None:
        max_seconds = 6.0
    last_exc: Optional[Exception] = None
    for backend in backends:
        if time.monotonic() - start >= max_seconds:
            break
        try:
            results: List[Dict[str, str]] = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, region=region, max_results=depth,
                                   backend=backend):
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("href", "") or r.get("url", ""),
                        "body": (r.get("body") or r.get("snippet") or ""),
                    })
            if results:
                return results
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            # A refused local proxy / missing DNS record / rate-limit is not
            # going to heal within the retry window — move to the next engine.
            continue
    if last_exc is not None:
        logger.warning("probe search failed for %r: %s", query, last_exc)
    return []


# ---------------------------------------------------------------------------
# Domain / brand helpers
# ---------------------------------------------------------------------------

_PARKED_PAT = re.compile(
    r"domain (name )?is for sale|buy this domain|this domain (name )?is for"
    r" sale|domain for sale|parked|parking page|nametrade|afternic|"
    r"sedo\.com|go[dD]addy|domain name marketplace|for sale on",
    re.I,
)


def _plausible_home(candidate: str, data: Optional[Dict[str, Any]]) -> bool:
    """Reject typo/parked domains that redirect off their registrable root
    or whose content is an obvious 'domain for sale' page."""
    if not data or not (data.get("html") or ""):
        return False
    reg = _registrable_domain(candidate)
    fin = _registrable_domain((data.get("final_url") or candidate or ""))
    if not reg or fin != reg:
        return False  # thehindu.net → nametrade.biz: parked, not a brand site
    sample = ((data.get("title") or "") + " " +
              (data.get("html") or "")[:4000]).lower()
    if _PARKED_PAT.search(sample):
        return False
    return True


def _domain(url: str) -> str:
    try:
        netloc = urlparse(url if "://" in url else "http://" + url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:  # noqa: BLE001
        return ""


def _registrable_domain(url: str) -> str:
    """Best-effort registrable domain (drop subdomains like blog/www/app)."""
    dom = _domain(url)
    parts = dom.split(".")
    if len(parts) > 2:
        return ".".join(parts[-2:])
    return dom


def _brand_from_domain(url: str) -> str:
    dom = _registrable_domain(url)
    base = dom.split(".")[0] if dom else ""
    words = re.split(r"[-_]", base)
    brand = " ".join(w.capitalize() for w in words if w)
    # camelCase split for single-word domains like "openai" → "Open AI"
    if len(brand.split()) == 1 and brand and len(brand) > 6:
        brand = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", brand)
        brand = " ".join(w.capitalize() for w in brand.split() if w)
    return brand


def _clean_brand(name: str) -> str:
    name = re.sub(r"\s*[|·•]\s*.*$", "", name)
    name = re.sub(r"\s+[-–—]\s+.*$", "", name)
    name = re.sub(r"\b(home|official website|official site|homepage)\b",
                  "", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip()


# ---------------------------------------------------------------------------
# HTML / meta / structured-data / link extraction
# ---------------------------------------------------------------------------

def _extract_meta(html: str) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for key in ("description", "keywords", "og:title", "og:description",
                "og:site_name", "og:locale", "author", "geo.region",
                "geo.placename", "dc.coverage"):
        pat = (r'<meta[^>]+(?:name|property)=["\']' + re.escape(key) +
               r'["\'][^>]+content=["\'](.*?)["\']')
        alt = (r'<meta[^>]+content=["\'](.*?)["\'][^>]+(?:name|property)=["\']'
               + re.escape(key) + r'["\']')
        m = re.search(pat, html, re.I | re.S) or re.search(alt, html, re.I | re.S)
        if m:
            meta[key] = m.group(1).strip()
    return meta


def _meta_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return m.group(1).strip() if m else ""


def _html_lang(html: str) -> Optional[str]:
    m = re.search(r'<html[^>]*\blang=["\']([a-zA-Z]{2,12})["\']', html, re.I)
    return m.group(1).lower() if m else None


def _canonical(html: str) -> Optional[str]:
    m = re.search(r'<link[^>]*rel=["\']canonical["\'][^>]*>', html, re.I)
    if not m:
        return None
    h = re.search(r'href=["\']([^"\']+)["\']', m.group(0), re.I)
    return h.group(1) if h else None


def _discover_feeds(html: str, base: str) -> List[str]:
    """RSS / Atom / JSONFeed links declared in <head>."""
    feeds: List[str] = []
    pat = (r'<link[^>]*(?:rel=["\']alternate["\']|type=["\']application/(?:rss|atom|\+json)'
           r'(?:\+xml)?["\'])[^>]*>')
    for m in re.finditer(pat, html, re.I):
        tag = m.group(0)
        rel = re.search(r'rel=["\']([^"\']+)["\']', tag, re.I)
        typ = re.search(r'type=["\']([^"\']+)["\']', tag, re.I)
        href = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
        if not href:
            continue
        if rel and "alternate" not in rel.group(1).lower():
            continue
        if typ and not any(k in typ.group(1).lower()
                           for k in ("rss", "atom", "json")):
            continue
        u = _absolutize(href.group(1), base)
        if u:
            feeds.append(u)
    return _dedupe(feeds, limit=6)


def _extract_links(html: str, base: str) -> List[Tuple[str, str]]:
    """All (anchor_text, href) pairs on the page."""
    out: List[Tuple[str, str]] = []
    for m in re.finditer(r"<a\b[^>]*>(.*?)</a>", html, re.I | re.S):
        tag = m.group(0)
        h = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
        if not h:
            continue
        href = _absolutize(h.group(1), base)
        if not href:
            continue
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append((text, href))
    return out


def _extract_jsonld(html: str) -> Dict[str, Any]:
    """Best-effort schema.org JSON-LD extraction.

    Returns {'orgs': [...], 'categories': [...], 'names': [...], 'types': [...]}.
    """
    orgs: List[str] = []
    categories: List[str] = []
    names: List[str] = []
    types: List[str] = []
    blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\']>(.*?)</script>',
        html, re.I | re.S,
    )
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        try:
            data = json.loads(block)
        except Exception:  # noqa: BLE001
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            g = node.get("@graph")
            if isinstance(g, list):
                nodes.extend(n for n in g if isinstance(n, dict))
                continue
            t = node.get("@type") or node.get("type") or ""
            t = t if isinstance(t, str) else (
                " ".join(t) if isinstance(t, list) else "")
            name = node.get("name") or ""
            if t:
                for tt in t.split():
                    if tt.lower() not in types:
                        types.append(tt.lower())
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
                tl = t.lower()
                if any(k in tl for k in ("organization", "corporation", "company",
                                         "localbusiness", "softwareapplication",
                                         "product", "brand", "store", "shop",
                                         "clin", "restaurant", "hotel", "bank")):
                    orgs.append(name.strip())
            for key in ("category", "genre", "sector"):
                v = node.get(key)
                if isinstance(v, str) and v.strip():
                    categories.append(v.strip())
                elif isinstance(v, list):
                    categories.extend(c.strip() for c in v if isinstance(c, str) and c.strip())
            about = node.get("about")
            if isinstance(about, dict):
                bn = about.get("name")
                if isinstance(bn, str) and bn.strip():
                    categories.append(bn.strip())
            bread = node.get("itemListElement")
            if isinstance(bread, list):
                for el in bread:
                    if isinstance(el, dict):
                        nm = el.get("name")
                        if isinstance(nm, str) and 2 <= len(nm) <= 50:
                            categories.append(nm.strip())
    return {
        "orgs": _dedupe(orgs, limit=8),
        "categories": _dedupe(categories, limit=10),
        "names": _dedupe(names, limit=8),
        "types": _dedupe(types, limit=12),
    }


def _nav_categories(html: str, base: str) -> List[str]:
    """Keywords from navigation / header link labels (products, services...)."""
    cats: List[str] = []
    seen: set = set()
    for text, href in _extract_links(html, base):
        if not (3 <= len(text) <= 42):
            continue
        low = text.lower()
        if low in seen or low in _STOPWORDS or _looks_like_nav(low):
            continue
        # skip pure verbs / generic boilerplate
        if low in {"click here", "read more", "learn more", "view all", "see all",
                   "get started", "sign in", "sign up", "pricing", "home"}:
            continue
        seen.add(low)
        cats.append(re.sub(r"\s+", " ", text))
        if len(cats) >= 8:
            break
    return cats


def _clean_html_text(html: str) -> str:
    try:
        from ..harvester.cleaner import extract_text

        return extract_text(html)
    except Exception:  # noqa: BLE001
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "noscript", "header",
                             "footer", "nav", "aside", "form", "svg"]):
                tag.decompose()
            main = soup.find("article") or soup.find("main") or soup.body
            return (main.get_text(separator=" ") if main else "") or ""
        except Exception:  # noqa: BLE001
            return ""


# ---------------------------------------------------------------------------
# Topic / keyword derivation
# ---------------------------------------------------------------------------

_HEADING_TAG = re.compile(r"<(h[1-3]|title)[^>]*>(.*?)</\1>", re.I | re.S)


def _looks_like_nav(s: str) -> bool:
    low = s.lower()
    nav = ("home", "about us", "contact", "privacy", "terms", "sitemap",
           "cookie", "sign in", "sign up", "login", "register", "menu",
           "footer", "newsletter", "careers", "faq", "help", "search",
           "products", "services", "blog", "cart", "checkout",
           "subscribe", "subscription", "my account", "myprofile",
           "manage subscription", "digest", "epaper", "e-paper",
           "download the app", "download app", "get the app", "get app",
           "advertise", "advertise with", "customer support", "feedback",
           "write to us", "newsdesk", "read more")
    return any(low.startswith(n) or low == n for n in nav)


def _topics_from_html(html: str, text: str, title: str) -> List[str]:
    candidates: List[str] = []
    meta = _extract_meta(html)
    kw = meta.get("keywords", "")
    if kw:
        for k in kw.split(","):
            k = k.strip()
            if 3 <= len(k) <= 60:
                candidates.append(k)
    if title:
        t = _clean_brand(title)
        if 3 <= len(t) <= 60:
            candidates.append(t)

    jd = _extract_jsonld(html)
    candidates.extend(jd["categories"])
    candidates.extend(jd["orgs"])

    for _tag, inner in _HEADING_TAG.findall(html):
        inner = re.sub(r"<[^>]+>", "", inner)
        inner = re.sub(r"\s+", " ", inner).strip()
        if 3 <= len(inner) <= 60 and not _looks_like_nav(inner):
            candidates.append(inner)

    if text:
        sentences = re.split(r"(?<=[.!?])\s+", text[:3000])
        for sent in sentences[:8]:
            sent = re.sub(r"\s+", " ", sent).strip()
            words = sent.split()
            if 3 <= len(words) <= 10 and 3 <= len(sent) <= 60:
                candidates.append(sent)

    return _dedupe(candidates, limit=14)


def _clean_title(raw: str) -> str:
    """Strip trailing site-name suffixes ('Foo Bar - GitHub', 'Foo · GitHub')
    and stray separators so titles read as plain phrases."""
    s = raw.strip()
    s = re.sub(r"\s*[-|·—]\s*([A-Z][A-Za-z0-9&'\. ]{1,40})$", "", s)
    for sep in (" - ", " | ", " · ", " — ", " ~ "):
        if sep in s:
            s = s.split(sep)[0].strip()
    return s.strip("'\" -|·—")


def _topics_from_search(
    brand: str, max_seconds: Optional[float] = 6.0
) -> List[str]:
    """Single 'industry' query; a 'products' fallback only when too thin."""
    brand_l = brand.lower()
    titles: List[str] = []
    for q in (f"{brand} industry",):
        for r in _search(q, depth=6, max_seconds=max_seconds):
            t = _clean_title(r.get("title", ""))
            if t and t.lower() != brand_l and not _looks_like_nav(t):
                titles.append(t)
    if len(titles) < 3:
        for q in (f"{brand} products", f"{brand} services"):
            for r in _search(q, depth=4, max_seconds=max_seconds):
                t = _clean_title(r.get("title", ""))
                if t and t.lower() != brand_l and not _looks_like_nav(t):
                    titles.append(t)
            if len(titles) >= 3:
                break
    topics = _dedupe(titles, limit=10)
    topics = [x for x in topics if 2 <= len(x.split()) <= 6]
    if not topics:
        topics = [f"{brand} industry"]
    return topics


# ---------------------------------------------------------------------------
# Competitor derivation
# ---------------------------------------------------------------------------

_COMPARE_PAT = re.compile(
    r"(?:vs\.?|versus|alternative[s]?\s+to|competitor[s]?\s*(?:of|for|to|:)?|"
    r"compared? to|compared? with|rather than|instead of|like)\s+"
    r"([A-Z][A-Za-z0-9&'’\.\- ]{1,60})",
    re.I,
)


_ORG_SUFFIX_RE = re.compile(
    r"(?:Inc|Inc\.|Corp|Corporation|Ltd|LLC|Co|Group|Holdings|Technologies|"
    r"Technology|Software|Solutions|Systems|System|Labs|Lab|Media|Networks|"
    r"Bank|Insurance|Ins|Health|Electric|Motors|Motor|Airways|Airlines|"
    r"Airlines|Express|Gillette|Industries|Enterprises|Digital|Cloud|AI|"
    r"Energy|Finance|Investments|Logistics|Retail|Food|Drinks|Club|Studio|"
    r"Works|Games|Market|Shop|Store|Global|International|Intl)\b",
    re.I,
)

_SINGLE_ORG_STOP = {
    "alternatives", "alternative", "hosted", "hosting", "self", "aug",
    "explore", "home", "about", "blog", "read", "more", "learn", "free",
    "new", "best", "top", "now", "get", "sign", "login", "join", "view",
    "watch", "listen", "shop", "buy", "price", "pricing", "docs",
    "documentation", "guide", "guides", "tutorial", "tutorials", "how",
    "why", "what", "which", "where", "when", "review", "reviews", "news",
    "open", "start", "started", "see", "all", "use", "using", "used",
    "our", "you", "your", "try", "test", "demo", "live", "platform",
    "software", "feature", "features", "support", "help", "contact",
    "faq", "page", "site", "official", "origin", "code", "repo", "data",
    "cloud", "digital", "energy", "retail", "food", "drinks", "logistics",
    "finance", "health", "insurance", "bank", "media", "network", "networks",
    "holdings", "group", "global", "international", "technology",
    "technologies", "solutions", "systems", "labs", "studio", "works",
    "market", "shop", "store", "club", "games", "cloud", "storage", "sec",
    "graphics", "computing", "services", "service", "review", "ebook",
    "competitors", "competitor", "compete", "comparison", "compare",
    "complete", "list", "ratings", "rating", "ranking", "rankings",
    "examples", "example", "domain", "domains", "pricing", "price", "prices",
    "overview", "related", "people", "questions", "stats", "statistics",
    "profile", "profiles", "revenue", "employees", "founded", "website",
    "links", "products", "product", "features", "screenshots", "tags",
    "seo", "checkup", "checker", "checkers", "finder", "url", "semrush",
    "ahrefs", "moz", "similarweb", "similar", "sites", "aboutthis",
    "find", "want", "need", "make", "build", "create", "story", "stories",
    "way", "ways", "thing", "things", "everything", "anyone", "everyone",
    "today", "yesterday", "tomorrow", "week", "month", "year",
    "avoid", "choose", "prefer", "select", "compare", "need", "want",
    "must", "should", "will", "can", "make", "use", "taking", "getting",
    "provide", "provides", "offers", "offer", "aboutthis", "know", "see",
}


_ORG_BAIT_WORDS = {
    "sites", "site", "like", "similar", "alternatives", "alternative",
    "saas", "directory", "database", "listing", "listings", "top",
    "best", "review", "reviews", "tools", "software", "apps", "app",
    "platform", "platforms", "versus", "compare", "comparison", "online",
}


def _extract_org_phrases(text: str, brand: str = "") -> List[str]:
    """Naive capitalized-entity extraction producing brand-like phrases.

    Captures 1-3 consecutive Capitalized words ('Under Armour', 'New Balance',
    'Acme Corp'), then filters hard:

    * single-word matches must be acronyms / org-suffixed / followed by a comma
      (i.e. they read as an item in a brand list) and must NOT be common words,
    * multi-word matches must not start or end with generic title words
      ('Top', 'Best', 'Competitors', 'Review', 'Analysis', ...) and must not
      be sentence openers.

    If ``brand`` is given, tokens belonging to the brand are skipped too.
    """
    brand_tokens = {w.lower() for w in brand.split() if w} if brand else set()
    first_reject = {"top", "best", "how", "why", "what", "this", "that",
                    "these", "those", "the", "a", "an", "most", "more",
                    "all", "your", "our", "their", "are", "do", "where",
                    "when", "which", "learn", "read", "find", "get", "view",
                    "see", "is", "are", "was", "were", "have", "has",
                    "did", "does", "had", "will", "would", "could", "should",
                    "can", "per", "for", "via", "with", "from", "into",
                    "days", "weeks", "hours", "minutes", "free", "also",
                    "10", "11", "12", "13", "14", "15", "20", "25", "5", "7",
                    "8", "9", "6"}
    last_reject = {"competitors", "alternatives", "comparison", "comparisons",
                   "reviews", "tools", "software", "companies", "market",
                   "markets", "analysis", "list", "guide", "guides", "options",
                   "solutions", "platforms", "services", "products", "pricing",
                   "features", "near", "rating", "ratings", "rankings",
                   "ranking", "valuation", "coverage", "profile", "revenue",
                   "funding", "employees", "overview", "company", "industry",
                   "industries", "sector", "sectors", "category",
                   "top", "best", "overview", "review", "common", "each",
                   "example", "examples", "2026", "2025", "2024", "2023",
                   "day", "week", "month", "year", "authority", "data",
                   "database", "search", "engine", "engines", "queries"}
    phrases: List[str] = []
    for m in re.finditer(
        r"\b([A-Z][A-Za-z0-9&'’]+(?:\s+[A-Z][A-Za-z0-9&'’]+){0,2})\b",
        text,
    ):
        p = m.group(1).strip()
        if not p or _looks_like_nav(p) or p.lower() in _STOPWORDS:
            continue
        words = p.split()
        # generic listing/aggregator bait words ('Sites Like The',
        # 'SaaS Discovery', 'Top Alternatives') are never brand names
        if any(w.lower() in _ORG_BAIT_WORDS for w in words):
            continue
        if len(words) == 1:
            low = p.lower()
            if low in _SINGLE_ORG_STOP or low in brand_tokens:
                continue
            if p.isupper() and len(p) >= 2:
                pass  # acronym ('IBM', 'XRP', 'AI')
            elif _ORG_SUFFIX_RE.search(low):
                pass  # corporate suffix ('Acme Inc.' split as 'Acme Inc' 2 words; single 'Inc' here is rare)
            elif len(p) < 4:
                continue
            elif text[m.end():].lstrip().startswith(","):
                pass  # appeared as an item in a comma list ('Adidas, Puma,')
            else:
                continue  # lone generic Capitalized word → junk
        else:
            first = words[0].lower().strip(".,;:!?")
            last = words[-1].lower().strip(".,;:!?")
            if first in first_reject or last in last_reject:
                continue
            if any(re.search(r"[\d]", w) for w in words[1:]):
                continue
            # skip phrases that are really still just the brand ('Nike Nike')
            if all(w.lower() in brand_tokens for w in words):
                continue
            if any(w.lower() in brand_tokens for w in words[1:]):
                # 'Brand Competitors' style pieces become single-brand skips
                continue
            # reject small-c raw fragments like '<Brand> Ltd' handled above;
            # also require at least one alphabetic char obviously already true
            pass
        # forbid punctuation-only or bracketed leftovers
        p2 = re.sub(r"[^A-Za-z0-9&'’ .-]", "", p).strip(" .-")
        if len(p2) < 2:
            continue
        phrases.append(p2)
    return _dedupe(phrases, limit=16)


def _competitors_on_page(text: str, brand: str) -> List[str]:
    comps: List[str] = []
    brand_l = brand.lower()
    for m in _COMPARE_PAT.finditer(text):
        raw = m.group(1).strip()
        for part in raw.split(","):
            part = part.strip()
            if not part or not part[0].isupper():
                continue
            words = part.split()
            if len(words) == 1 and len(part) < 4:
                continue
            if part.lower() == brand_l or brand_l in part.lower():
                continue
            comps.append(re.sub(r"\s+", " ", part))
    return _dedupe([c for c in comps if 3 <= len(c) <= 40], limit=8)


# Generic single/common nouns that search-result parsing mistakes for rival
# brand names (nav labels, section names, CTAs). A candidate is rejected when
# it IS one of these, or when EVERY word in it is generic — so "News UK" and
# "KM Media Group" survive (UK/KM are distinctive) while "Funding" dies.
_GENERIC_ENTITY_WORDS = frozenset({
    "funding", "news", "media", "group", "company", "companies", "home",
    "about", "contact", "contacts", "subscribe", "subscription", "login",
    "signin", "signup", "register", "press", "careers", "jobs", "blog",
    "blogs", "shop", "store", "support", "help", "privacy", "terms",
    "cookies", "cookie", "menu", "search", "topics", "sections", "edition",
    "editions", "live", "breaking", "opinion", "sport", "sports", "culture",
    "lifestyle", "travel", "tech", "technology", "business", "money",
    "markets", "market", "videos", "video", "podcasts", "podcast",
    "newsletters", "newsletter", "archive", "sitemap", "account", "profile",
    "settings", "read", "more", "view", "all", "sign", "click", "here",
    "limited", "services", "solutions", "official", "site", "website",
})


def _clean_entity_name(name: str) -> str:
    """Split camelCase concatenations from nav labels into real words."""
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name or "")
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .-")


def _is_generic_entity(name: str) -> bool:
    words = [w.strip(".,;:!?()").lower() for w in (name or "").split()]
    words = [w for w in words if w]
    if not words:
        return True
    return all(w in _GENERIC_ENTITY_WORDS for w in words)


_CTA_FIRST_WORDS = frozenset({
    "discover", "explore", "visit", "read", "shop", "buy", "get", "download",
    "join", "sign", "follow", "watch", "listen", "try", "start", "compare",
    "meet", "see", "find",
})


def _sanitize_entities(names: List[str], brand: str) -> List[str]:
    """Normalize + drop generic/junk entity candidates (never invent any)."""
    out: List[str] = []
    brand_l = (brand or "").lower()
    brand_clean = _clean_entity_name(brand).lower()
    brand_words = set(brand_l.split()) | set(brand_clean.split())
    for n in names or []:
        c = _clean_entity_name(n)
        if not c or len(c) < 3 or len(c) > 48:
            continue
        if c.lower() in (brand_l, brand_clean) or brand_l in c.lower() \
                or (brand_clean and brand_clean in c.lower()):
            continue
        words = [w.strip(".,;:!?()").lower() for w in c.split()]
        words = [re.sub(r"['’]s$", "", w) for w in words]
        words = [w for w in words if w]
        if not words:
            continue
        if words[0] in _CTA_FIRST_WORDS:
            continue  # "Discover The Guardian" — CTA copy, not a rival
        if _is_generic_entity(" ".join(words)):
            continue
        # brand-stem overlap ("Guardian News" vs brand "Theguardian") means
        # brand family / house brand, never a competitor.
        if any(len(w) > 4 and any(w in bw or bw in w for bw in brand_words)
               for w in words):
            continue
        out.append(c)
    return _dedupe(out, limit=8)


def _competitors_from_search(
    brand: str, max_seconds: Optional[float] = 6.0
) -> List[str]:
    """Budgeted 'competitors' (+ 'alternatives' fallback) so real rival names
    surface even when on-page comparison prose is thin."""
    comps: List[str] = []
    brand_l = brand.lower()
    for q in (f"{brand} competitors",):
        for r in _search(q, depth=6, max_seconds=max_seconds):
            for raw in (r.get("title", ""), r.get("body", "")):
                for p in _extract_org_phrases(raw, brand):
                    if p.lower() == brand_l or brand_l in p.lower():
                        continue
                    comps.append(p)
    if len(comps) < 4:
        for q in (f"{brand} alternatives",):
            for r in _search(q, depth=5, max_seconds=max_seconds):
                for raw in (r.get("title", ""), r.get("body", "")):
                    for p in _extract_org_phrases(raw, brand):
                        if p.lower() == brand_l or brand_l in p.lower():
                            continue
                        comps.append(p)
    return _dedupe([c for c in comps if c.lower() != brand_l], limit=10)


# ---------------------------------------------------------------------------
# Locality / geo derivation
# ---------------------------------------------------------------------------

_GEO_META = re.compile(
    r'<(?:meta\s+name=["\'](?:geo\.?region|geo\.?placename|dc\.?coverage|'
    r'og:locale)["\'][^>]*content=["\']|html[^>]*lang=["\'])([^"\']+)',
    re.I,
)

_TLD_COUNTRY = {
    "us": "US", "uk": "UK", "gb": "UK", "ca": "CA", "au": "AU",
    "in": "IN", "de": "DE", "fr": "FR", "nl": "NL", "es": "ES",
    "it": "IT", "br": "BR", "mx": "MX", "sg": "SG", "jp": "JP",
    "cn": "CN", "ae": "AE", "za": "ZA", "nz": "NZ", "ie": "IE",
    "se": "SE", "no": "NO", "dk": "DK", "fi": "FI", "ch": "CH",
    "at": "AT", "be": "BE", "pt": "PT", "pl": "PL", "kz": "KZ",
    "ua": "UA", "tr": "TR", "il": "IL", "my": "MY", "id": "ID",
    "th": "TH", "vn": "VN", "ph": "PH", "kr": "KR", "tw": "TW",
    "hk": "HK", "ru": "RU",
}

# alphabetic ISO-3166-1 alpha-2 codes we accept as a country signal (so a bare
# 2-letter *language* tag like "en" / "fr" is never mistaken for a country)
_ISO_COUNTRY = set(_TLD_COUNTRY.values()) | {"UK", "US", "GB"}

_LANG_COUNTRY = {
    "en-us": "US", "en-gb": "UK", "en-ca": "CA", "en-au": "AU",
    "en-in": "IN", "en-sg": "SG", "en-nz": "NZ", "en-za": "ZA",
    "de-de": "DE", "de-at": "AT", "de-ch": "CH", "fr-fr": "FR",
    "fr-ca": "CA", "fr-be": "BE", "es-es": "ES", "es-mx": "MX",
    "es-ar": "AR", "it-it": "IT", "pt-br": "BR", "pt-pt": "PT",
    "nl-nl": "NL", "nl-be": "BE", "pl-pl": "PL", "ja-jp": "JP",
    "ko-kr": "KR", "zh-cn": "CN", "zh-tw": "TW", "zh-hk": "HK",
    "ru-ru": "RU", "tr-tr": "TR", "sv-se": "SE", "da-dk": "DK",
    "fi-fi": "FI", "no-no": "NO", "cs-cz": "CZ", "el-gr": "GR",
    "ar-ae": "AE", "hi-in": "IN", "id-id": "ID", "th-th": "TH",
    "vi-vn": "VN", "ms-my": "MY", "fil-ph": "PH",
}

_CITY_COUNTRY = {
    "mumbai": "IN", "delhi": "IN", "new delhi": "IN", "bengaluru": "IN",
    "bangalore": "IN", "chennai": "IN", "hyderabad": "IN", "pune": "IN",
    "kolkata": "IN", "gurgaon": "IN", "noida": "IN", "london": "UK",
    "manchester": "UK", "birmingham": "UK", "leeds": "UK", "edinburgh": "UK",
    "glasgow": "UK", "toronto": "CA", "vancouver": "CA", "montreal": "CA",
    "ottawa": "CA", "calgary": "CA", "sydney": "AU", "melbourne": "AU",
    "brisbane": "AU", "perth": "AU", "adelaide": "AU", "auckland": "NZ",
    "singapore": "SG", "tokyo": "JP", "osaka": "JP", "hong kong": "HK",
    "seoul": "KR", "shanghai": "CN", "beijing": "CN", "shenzhen": "CN",
    "paris": "FR", "lyon": "FR", "marseille": "FR", "berlin": "DE",
    "munich": "DE", "hamburg": "DE", "frankfurt": "DE", "madrid": "ES",
    "barcelona": "ES", "milan": "IT", "rome": "IT", "amsterdam": "NL",
    "rotterdam": "NL", "brussels": "BE", "zurich": "CH", "geneva": "CH",
    "stockholm": "SE", "oslo": "NO", "copenhagen": "DK", "helsinki": "FI",
    "warsaw": "PL", "prague": "CZ", "vienna": "AT", "dublin": "IE",
    "lisbon": "PT", "athens": "GR", "istanbul": "TR", "dubai": "AE",
    "abu dhabi": "AE", "riyadh": "SA", "cairo": "EG", "lagos": "NG",
    "nairobi": "KE", "são paulo": "BR", "sao paulo": "BR",
    "rio de janeiro": "BR", "mexico city": "MX", "buenos aires": "AR",
    "santiago": "CL", "bogota": "CO", "lima": "PE", "jakarta": "ID",
    "bangkok": "TH", "kuala lumpur": "MY", "manila": "PH", "moscow": "RU",
    "krakow": "PL", "miami": "US", "new york": "US", "chicago": "US",
    "los angeles": "US", "san francisco": "US", "seattle": "US",
    "austin": "US", "boston": "US", "atlanta": "US", "houston": "US",
}

# Order matters: unambiguous currency codes first, ambiguous '$' last.
_CURRENCY_COUNTRY = [
    (r"\binr\b", "IN"), (r"\brs\.?", "IN",), (r"₹", "IN"),
    (r"\bgbp\b", "UK"), (r"£", "UK"),
    (r"\baed\b", "AE"), (r"\bdirhams?\b", "AE"),
    (r"\bsgd\b", "SG"), (r"\bs\$", "SG"),
    (r"\bhkd\b", "HK"), (r"\bhk\$", "HK"),
    (r"\bmyr\b", "MY"), (r"\brm\b", "MY"),
    (r"\bthb\b", "TH"), (r"\b₫\b", "VN"),
    (r"\bidr\b", "ID"), (r"\bphp\b", "PH"),
    (r"\bczk\b", "CZ"), (r"\bpln\b", "PL"), (r"\bzł\b", "PL"),
    (r"\bnok\b", "NO"), (r"\bsek\b", "SE"), (r"\bdkk\b", "DK"),
    (r"\bchf\b", "CH"), (r"\bnzd\b", "NZ"),
    (r"\baud\b", "AU"), (r"\ba\$", "AU"),
    (r"\bcad\b", "CA"), (r"\bc\$", "CA"),
    (r"\bczk\b", "CZ"), (r"\bilr\b", "IL"), (r"₪", "IL"),
    (r"\b₩\b", "KR"), (r"¥", None), (r"\b€\b", None), (r"\br\$", "BR"),
    (r"\brand\b", "ZA"), (r"\bzar\b", "ZA"),
    (r"\b\$", None),
]


def _locality_from_site(html: str, url: str, text: str = "") -> Optional[str]:
    for m in _GEO_META.finditer(html):
        val = m.group(1).strip()
        val_l = val.lower()
        if val_l in _LANG_COUNTRY:
            return _LANG_COUNTRY[val_l]
        if len(val) <= 3:
            if val.upper() in _ISO_COUNTRY:
                return val.upper()
            continue  # 2-letter language code like "en" is NOT a country
        if "," in val:
            last = val.split(",")[-1].strip()
            if len(last) == 2 and last.upper() in _ISO_COUNTRY:
                return last.upper()
    lang = _html_lang(html)
    if lang:
        if lang in _LANG_COUNTRY:
            return _LANG_COUNTRY[lang]
        code = lang.split("-")
        if len(code) > 1 and len(code[1]) == 2 and \
                code[1].upper() in _ISO_COUNTRY:
            return code[1].upper()
    # address / city mentions are strong locality evidence
    low = (text or "").lower()
    for city, country in _CITY_COUNTRY.items():
        if re.search(r"\b" + re.escape(city) + r"\b", low):
            return country
    # unambiguous currency markers
    for pattern, country in _CURRENCY_COUNTRY:
        if country is None:
            continue
        if re.search(pattern, low):
            return country
    # repeated country self-reference on the homepage is a strong locale hint
    # ('india news' pages, .in publishers, etc.)
    if re.search(r"\bindia\b", low) and not re.search(r"\bus(?:a)?\b", low[:2000]):
        return "IN"
    # TLD
    dom = _registrable_domain(url)
    tld = dom.split(".")[-1].lower() if "." in dom else ""
    if tld in _TLD_COUNTRY:
        return _TLD_COUNTRY[tld]
    if re.search(r"\busd\b", low):
        return "US"
    return None


def _country_hint(text: str) -> Optional[str]:
    """Try to pull a country out of free prose (search snippets, 'HQ in ...')."""
    low = (text or "").lower()
    for city, country in _CITY_COUNTRY.items():
        if re.search(r"\b" + re.escape(city) + r"\b", low):
            return country
    for name, code in {"germany": "DE", "france": "FR", "india": "IN",
                       "united kingdom": "UK", "uk": "UK", "me": "UK",
                       "canada": "CA", "australia": "AU", "japan": "JP",
                       "china": "CN", "brazil": "BR", "mexico": "MX",
                       "singapore": "SG", "spain": "ES", "italy": "IT",
                       "netherlands": "NL", "switzerland": "CH", "sweden": "SE",
                       "norway": "NO", "denmark": "DK", "poland": "PL",
                       "russia": "RU", "turkey": "TR", "uae": "AE",
                       "saudi arabia": "SA", "south africa": "ZA",
                       "new zealand": "NZ", "united arab emirates": "AE",
                       "south korea": "KR", "korea": "KR", "thailand": "TH",
                       "vietnam": "VN", "malaysia": "MY", "indonesia": "ID",
                       "philippines": "PH", "argentina": "AR", "chile": "CL"}.items():
        if re.search(r"\b" + re.escape(name) + r"\b", low):
            return code
    return None


# ---------------------------------------------------------------------------
# Language / script detection (for embedding + spaCy model choice)
# ---------------------------------------------------------------------------

_NON_LATIN = re.compile(
    r"[\u0400-\u04FF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF\u0590-\u05FF"
    r"\u0600-\u06FF\u0900-\u097F\u0A00-\u0A7F\u0B00-\u0B7F\u0C00-\u0C7F"
    r"\u0D00-\u0D7F\u0E00-\u0E7F\u0E80-\u0EFF\u10A0-\u10FF\u30A0-\u30FA]+",
    re.I,
)


def _language_hints(text: str) -> Tuple[Optional[str], bool]:
    """Return (lang code guessed from script, multilingual flag)."""
    sample = text[:6000]
    if not sample:
        return None, False
    letters = [ch for ch in sample if ch.isalpha()]
    if not letters:
        return None, False
    nonlat = len(_NON_LATIN.findall(sample))
    ratio = (sum(len(m) for m in _NON_LATIN.findall(sample)) /
             max(1, len(letters)))
    if ratio > 0.05:
        if re.search(r"[\u4E00-\u9FFF]", sample):
            return "zh", True
        if re.search(r"[\u3040-\u30FF]", sample):
            return "ja", True
        if re.search(r"[\uAC00-\uD7AF]", sample):
            return "ko", True
        if re.search(r"[\u0600-\u06FF]", sample):
            return "ar", True
        if re.search(r"[\u0400-\u04FF]", sample):
            return "ru", True
        if re.search(r"[\u0900-\u097F]", sample):
            return "hi", True
        if re.search(r"[\u0590-\u05FF]", sample):
            return "he", True
        if re.search(r"[\u0E00-\u0E7F]", sample):
            return "th", True
        if re.search(r"[\u10A0-\u10FF]", sample):
            return "ka", True
        return "xx", True
    return "en", False


# ---------------------------------------------------------------------------
# Sub-brand / ontology aliases + product names + entity weighting
# ---------------------------------------------------------------------------

def _ontology_from_page(text: str, brand: str):
    """Return (aliases list, product-ish names) for the brand."""
    aliases: List[str] = []
    products: List[str] = []
    # common words/delimiters that never start a product/sub-brand name
    reject = {"the", "this", "that", "these", "those", "and", "for", "with",
              "your", "our", "their", "visit", "welcome", "click", "home",
              "official", "contact", "all", "its", "you", "they", "it",
              "please", "get", "free", "best", "top", "read", "learn",
              "sign", "view", "see", "how", "why", "what", "when", "which",
              "where", "more", "new", "about", "discover", "shop", "buy",
              "browse", "login", "register", "checkout", "find", "your"}
    for m in re.finditer(
        r"\b" + re.escape(brand) + r"\s+([A-Z][A-Za-z0-9&'’€\-\+ ]{1,24})\b",
        text,
    ):
        p = m.group(1).strip()
        low = p.lower()
        first = p.split()[0].lower() if p.split() else ""
        if low in _STOPWORDS or first in reject or len(p) < 2:
            continue
        if re.search(r"(^|\s)(is|a |an |the|for)($|\s)", p.lower()):
            continue  # "<Brand> is ..." fragments are prose, not products
        aliases.append(f"{brand} {p}")
        products.append(p)
    return _dedupe(aliases, limit=8), _dedupe(products, limit=8)


def _site_size_indicators(html: str, scan: Dict[str, dict],
                          base_url: str) -> Tuple[Optional[int], bool]:
    """Return (approx. published-URL count from sitemap, has_news_feed)."""
    sitemap_html = ""
    for url, data in (scan or {}).items():
        if "sitemap" in url.lower():
            sitemap_html = (data or {}).get("html", "")
            break
    count = None
    if sitemap_html:
        locs = len(re.findall(r"<loc>", sitemap_html, re.I))
        if locs:
            count = locs
    has_news = bool(re.search(r"news-site-map|sitemapnews|\bnews\b", sitemap_html[:2000], re.I))
    if not has_news:
        has_news = bool(re.search(r"\bnews\b|sitemap", (html or "")[:4000], re.I))
    return count, has_news


def _crawl_depth(doc_count: Optional[int], has_news: bool, text_len: int,
                 default: int = 50) -> int:
    if doc_count is not None:
        if doc_count >= 200:
            return 200
        if doc_count >= 80:
            return 150
        if doc_count >= 30:
            return 100
        return default
    if has_news or text_len > 20_000:
        return 100
    return default


# --- Real-topic sources: news sitemaps, RSS feed slugs -----------------

def _extract_news_topics(html: str) -> List[str]:
    """Pull real headlines out of a Google news sitemap (<news:title>)."""
    out: List[str] = []
    for t in re.findall(r"<news:title>(.*?)</news:title>", html or "",
                        re.I | re.S):
        t = re.sub(r"<[^>]+>", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        if 4 <= len(t) <= 90:
            out.append(t)
    return _dedupe(out, limit=40)


def _sitemap_sub_targets(html: str, base: str) -> List[str]:
    """From a sitemap index (.xml listing other sitemaps) choose up to two
    topic-bearing sub-sitemaps to actually fetch (news/feed/products first)."""
    locs = [l.strip() for l in re.findall(r"<loc>\s*(.*?)\s*</loc>",
                                          html or "", re.I | re.S)]
    locs = [l for l in locs if l.startswith("http")]
    if not locs or len(locs) < 2 or "<sitemap>" not in (html or ""):
        return []
    prefer = [l for l in locs
              if re.search(r"news|article|feed|product|post", l, re.I)]
    return prefer[:2] if prefer else locs[:2]


def _topics_from_feed_urls(feeds: List[str]) -> List[str]:
    """Turn RSS feed hrefs into labelled topic names — a newspapers' /rss/sport.xml
    is a genuinely real 'Sports' topic, no scraping required."""
    out: List[str] = []
    for u in feeds or []:
        path = re.sub(r"^https?://[^/]+/", "", u).split("?")[0]
        parts = [p for p in path.split("/") if p][-2:]
        for p in parts:
            name = re.sub(r"\.(xml|rss|json|atom)$", "", p, re.I)
            name = name.replace("-", " ").replace("_", " ").strip()
            if not (2 <= len(name) <= 24) or any(c.isdigit() for c in name):
                continue
            low = name.lower()
            if low in _STOPWORDS or low in ("top", "latest", "feed",
                                            "feeds", "news", "home",
                                            "homepage", "front"):
                continue
            out.append(name.title())
    return _dedupe(out, limit=14)


# ---------------------------------------------------------------------------
# Search intent scoring
# ---------------------------------------------------------------------------

_INTENT_SIGNALS = {
    "transactional": (
        "buy ", " priced at", " pricing ", " order ", " subscription",
        " cost ", " price ", " purchase", " checkout", " add to cart",
        " get started", " free trial", " plans", " subscribe",
    ),
    "commercial": (
        "compare", " alternatives", " alternative", " features",
        " benefits", " vs. ", " versus", " testimonials", " reviews",
        " rating", " best ", " top ", " solutions", " uses cases",
    ),
    "navigational": (
        "download", " sign in", " login", " install", " app store",
        " play store", " get the app", " log in", " account",
    ),
    "local": (
        "store locator", " near me", " locations", " address", " contact us",
        " open now", " opening hours", " branch", " delivery", " directions",
        " find a store",
    ),
}


def _score_intent(text: str, default: str = "informational") -> str:
    low = (text or "").lower()
    scores = {intent: sum(low.count(k) for k in keys)
              for intent, keys in _INTENT_SIGNALS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return default
    return best


# ---------------------------------------------------------------------------
# Local service discovery (SearXNG / Ollama) + installed-model inventory
# ---------------------------------------------------------------------------

def _local_services(scan: Dict[str, dict]) -> Dict[str, str]:
    """Detect a reachable local Ollama / SearXNG from the scan bundle results."""
    found: Dict[str, str] = {}
    for url in ("http://localhost:11434/api/tags",
                "http://127.0.0.1:11434/api/tags"):
        if scan.get(url):  # a 200 response (any body) means Ollama is up
            found["ollama"] = "http://localhost:11434"
            break
    for url in ("http://localhost:8888/", "http://localhost:8080/",
                "http://127.0.0.1:8888/"):
        if scan.get(url):
            found["searxng"] = url
            break
    return found


def _installed_spacy_models() -> List[str]:
    try:
        import spacy
        from spacy.util import get_installed_models

        return sorted(get_installed_models())
    except Exception:  # noqa: BLE001
        return []


def _pick_embedding(lang: Optional[str], multilingual: bool) -> str:
    if multilingual or (lang and lang not in ("en", None)):
        # multilingual-capable model already cached on this box
        return "sentence-transformers/all-MiniLM-L6-v2"
    return "sentence-transformers/all-mpnet-base-v2"


# ---------------------------------------------------------------------------
# SERP footprints (concrete, fetchable source URLs)
# ---------------------------------------------------------------------------

def _build_footprints(base_url: str, links: List[Tuple[str, str]],
                       wiki_url: Optional[str]) -> List[str]:
    lines: List[str] = []
    lines.append(f"Google AI Overviews|official site|{base_url}")
    if wiki_url:
        lines.append(f"SearchGPT|Wikipedia|{wiki_url}")
    used = 1
    for text, href in links:
        if used >= 6:
            break
        if not _same_site(href, base_url) or href.strip("/") == base_url.strip("/"):
            continue
        low = text.lower()
        if len(text) > 44 or _looks_like_nav(text):
            continue
        engines = ("Perplexity", "Gemini", "Bing Copilot", "SearchGPT")
        engine = engines[used % len(engines)]
        label = re.sub(r"\s+", " ", text)[:38]
        lines.append(f"{engine}|{label}|{href}")
        used += 1
    return lines


def _wikipedia_url(brand: str) -> Optional[str]:
    """Best-effort Wikipedia URL for the brand via live search (verified)."""
    try:
        for r in _search(f"{brand} wikipedia", depth=4, max_seconds=5.0):
            href = r.get("href", "") or ""
            if "wikipedia.org/wiki/" in href:
                return href
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def probe(input_text: str, depth: int = 8) -> Dict[str, Any]:
    """Given a brand name or a URL, return auto-filled field defaults.

    Returns a dict keyed by the web form's input names so the UI can populate
    them directly.  Every derivable field is filled; genuinely undetectable
    fields (internal corpus paths) are omitted and reported in ``_meta``.
    """
    input_text = (input_text or "").strip()
    if not input_text:
        return {}

    is_url = "://" in input_text or input_text.startswith("www.") or bool(
        re.match(
            r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}?\.)+[a-z]{2,}(?:[\/?#][^\s]*)?)$",
            input_text,
            re.I,
        )
    )
    url = None
    brand_hint = None
    candidates: List[str] = []
    if is_url:
        url = input_text if "://" in input_text else "https://" + input_text
        candidates = [url]
    else:
        brand_hint = input_text
        # brand-only input: probe the plausible registrable domains in
        # parallel and use whichever actually responds ('thehindu' → thehindu.com)
        slug = re.sub(r"[^a-z0-9]", "", brand_hint.lower())
        candidates = [
            f"https://{slug}.com",
            f"https://www.{slug}.com",
            f"https://{slug}.org",
            f"https://{slug}.net",
            f"https://{slug}.co",
        ]
    dom = _domain(url) if url else (_domain(candidates[0]) if candidates else None)
    base_url = url or (candidates[0] if candidates else f"https://{input_text}")
    if not base_url.startswith("http"):
        base_url = "https://" + base_url

    deadline = time.monotonic() + _PROBE_BUDGET

    def _remaining():
        return max(2.0, deadline - time.monotonic())

    fetched: Optional[Dict[str, Any]] = None
    scan: Dict[str, dict] = {}

    def _do_home():
        nonlocal fetched, url
        if url:
            fetched = _fetch_url_safe(url, budget=_HOME_FETCH_BUDGET)
            return
        # brand-only: probe candidate domains in two phases, each candidate in
        # its own hard-timeout sub-process.  Most brands live on {slug}.com, so
        # the .com pair is raced first; the exotic TLDs (.org/.net/.co) are
        # only tried if that yields nothing.  Racing 5 processes at once starves
        # the real site (observed: thehindu.com timed out at 7s under a 5-way
        # spawn), so keep concurrency low.
        picked: Dict[str, Dict[str, Any]] = {}

        def _race(domains: List[str], budget: float) -> None:
            round_pick: Dict[str, Dict[str, Any]] = {}

            def _w(cand: str) -> None:
                d = _fetch_url_safe(cand, budget=budget)
                if d and _plausible_home(cand, d):
                    round_pick[cand] = d

            workers = [threading.Thread(target=_w, args=(c,), daemon=True)
                       for c in domains]
            for t in workers:
                t.start()
            for t in workers:
                t.join(timeout=budget + 1.5)
            picked.update(round_pick)

        phases = [
            (candidates[:2], _HOME_FETCH_BUDGET),
            (candidates[2:], max(5.0, _HOME_FETCH_BUDGET - 2.0)),
        ]
        for domains, budget in phases:
            if not domains:
                continue
            if picked:
                break
            _race(domains, budget)
        if picked:
            best = max(picked, key=lambda c: len(picked[c].get("html") or ""))
            fetched = picked[best]
            url = best

    def _do_scan():
        nonlocal scan
        if not url:
            return
        targets = [
            _absolutize("/robots.txt", url),
            _absolutize("/sitemap.xml", url),
            _absolutize("/about", url),
            _absolutize("/about-us", url),
            _absolutize("/products", url),
            _absolutize("/services", url),
            _absolutize("/blog", url),
            _absolutize("/news", url),
            _absolutize("/contact", url),
            _absolutize("/feed", url),
            _absolutize("/rss.xml", url),
            "http://localhost:11434/api/tags",
            "http://localhost:8888/",
            "http://localhost:8080/",
        ]
        targets = [t for t in targets if t]
        scan = _fetch_many([t for t in targets if t], budget=_SCAN_BUDGET)

    th_home = threading.Thread(target=_do_home, daemon=True)
    th_scan = threading.Thread(target=_do_scan, daemon=True)
    scan_started = False
    th_home.start()
    if url:
        th_scan.start()
        scan_started = True

    # --- Resolve canonical brand from the strongest signal ----------------
    # do this after home fetch completes (title / og:site_name / JSON-LD)
    th_home.join(timeout=min(_HOME_FETCH_BUDGET * 2 + 1, _remaining()))
    brand = None
    meta = (fetched or {}).get("meta", {}) or {}
    # og:site_name is the canonical brand signal when present ('The Hindu')
    og_site = (_clean_brand(meta.get("og:site_name", "")) if meta else None)
    if og_site and 2 <= len(og_site) <= 42:
        brand = og_site
    if not brand and fetched and fetched.get("title"):
        brand = _clean_brand(fetched["title"])
        if (dom and brand and brand.lower() in (dom, dom.replace("www.", ""))):
            brand = _brand_from_domain(url or "")
    if not brand or len(brand) < 2:
        brand = _brand_from_domain(url) if url else None
    if not brand and brand_hint:
        brand = brand_hint
        # 'nike' → 'Nike' when the operator typed an all-lowercase hint
        if brand == brand.lower():
            brand = brand.title()
    if not brand:
        brands = _extract_org_phrases(input_text) or [input_text]
        brand = next((c.strip() for c in brands if len(c.strip()) >= 2), None)

    if not brand:
        return {}

    # a brand-only request that resolved to a live homepage (e.g. hint →
    # thehindu.com) gets its discovery scan started as soon as the domain is
    # known — searches below then overlap with it.
    if url and not scan_started:
        th_scan.start()
        scan_started = True

    # --- Run the budgeted web searches (overlaps page fetches) ------------
    # Deep-research grade: industry + products/services + competitors +
    # alternatives + vs-query + reviews, each budgeted, all live & verified.
    search_budget = min(_remaining(), 9.0)
    topics_from_srch = _topics_from_search(brand, max_seconds=search_budget)
    # enrich topics with services/products phrasing when thin
    if len(topics_from_srch) < 5:
        for q in (f"{brand} services", f"{brand} solutions", f"{brand} reviews"):
            for r in _search(q, depth=4, max_seconds=max(2.0, _remaining() * 0.3)):
                t = _clean_title(r.get("title", ""))
                if t and t.lower() != brand.lower() and not _looks_like_nav(t):
                    topics_from_srch.append(t)
            if len(topics_from_srch) >= 6:
                break
        topics_from_srch = _dedupe(topics_from_srch, limit=12)
    comps_from_srch = _competitors_from_search(
        brand, max_seconds=max(2.0, _remaining() * 0.5))
    # extra competitor pass: "{brand} vs" surfaces head-to-head rivals
    if len(comps_from_srch) < 5:
        for r in _search(f"{brand} vs", depth=6,
                         max_seconds=max(2.0, _remaining() * 0.3)):
            comps_from_srch += _extract_org_phrases(
                (r.get("body") or "") + " " + (r.get("title") or ""), brand)
        comps_from_srch = _dedupe(comps_from_srch, limit=12)

    if scan_started:
        th_scan.join(timeout=max(0.0, min(_SCAN_BUDGET, _remaining() - 2.0)))

    page_html = (fetched or {}).get("html", "") or ""
    page_meta = meta or {}
    page_text = _clean_html_text(page_html)
    final_url = (fetched or {}).get("final_url") or ""
    feeds = _discover_feeds(page_html, final_url or base_url) if page_html else []

    # --- Robots → sitemap → document count -------------------------------
    sitemap_url = None
    robots = ""
    for u, d in (scan or {}).items():
        if "robots" in u.lower():
            robots = (d or {}).get("html", "") or ""
    for line in robots.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            break
    if not sitemap_url:
        sitemap_url = _absolutize("/sitemap.xml", final_url or base_url)
    doc_count, has_news = _site_size_indicators(page_html, scan, base_url)

    # --- Real topics from news sitemaps (Google news feeds give actual
    #     current headlines — genuine 2026 editorial topics, not invented).
    news_topics: List[str] = []
    sitemap_body = ""
    for u, d in (scan or {}).items():
        if "sitemap" in u.lower() and (d or {}).get("html"):
            sitemap_body = d["html"]
            break
    if sitemap_body:
        if "<sitemap>" in sitemap_body:
            subs = _sitemap_sub_targets(sitemap_body, base_url)
            if subs:
                extra = _fetch_many(subs, budget=min(3.0, _remaining() * 0.5))
                for u, d in (extra or {}).items():
                    news_topics += _extract_news_topics((d or {}).get("html", ""))
        else:
            news_topics += _extract_news_topics(sitemap_body)
        if news_topics:
            has_news = True

    # --- Topics -----------------------------------------------------------
    topics: List[str] = []
    if fetched:
        topics += _topics_from_html(page_html, page_text,
                                    fetched.get("title", ""))
    nav = _nav_categories(page_html, final_url or base_url) if page_html else []
    topics += nav
    topics += _topics_from_feed_urls(feeds)
    topics += news_topics
    topics += topics_from_srch
    topics = [t for t in _dedupe(topics, limit=40)
              if _looks_like_nav(t.lower()) is False and t.lower() != brand.lower()]
    topics = [t for t in topics if 2 <= len(t.split()) <= 12]
    if not topics:
        topics = [f"{brand} industry"]

    # --- Competitors ------------------------------------------------------
    competitors: List[str] = []
    if fetched:
        competitors += _competitors_on_page(page_text, brand)
    competitors += comps_from_srch
    if not competitors:
        # backends are flaky minute-to-minute; one extra cheap pass
        for r in _search(f"{brand} rivals", depth=6,
                         max_seconds=max(2.0, _remaining() * 0.4)):
            c = _extract_org_phrases((r.get("body") or "") + " " +
                                     (r.get("title") or ""), brand)
            competitors += c
    competitors = _sanitize_entities(
        _dedupe(competitors, limit=12), brand)
    if not competitors and fetched:
        competitors = _sanitize_entities(
            [p for p in _extract_org_phrases(page_text)
             if p.lower() != brand.lower() and brand.lower() not in p.lower()],
            brand)
    competitors_incomplete = False
    if not competitors:
        # never invent placeholder names — flag for the UI instead
        competitors_incomplete = True

    # --- Locality ---------------------------------------------------------
    locality = None
    if fetched:
        locality = _locality_from_site(page_html, final_url or url or "",
                                       page_text) or _locality_from_site(
            page_html, final_url or url or "")
    if not locality and not url and brand_hint:
        for r in _search(f"{brand_hint} headquarters country", depth=3,
                         max_seconds=max(2.0, _remaining() * 0.4)):
            locality = _country_hint((r.get("body") or "") + " " +
                                     (r.get("title") or ""))
            if locality:
                break

    # --- Language / models ------------------------------------------------
    lang_html = _html_lang(page_html) if page_html else None
    lang, multilingual = _language_hints(page_text) if page_text else (lang_html, False)
    if not lang:
        lang = lang_html
    embedding_model = _pick_embedding(lang, multilingual)
    spacy_model = "en_core_web_sm"
    spacy_models = _installed_spacy_models()
    if spacy_models:
        for cand in (f"en_core_web_sm", f"en_core_web_md", f"en_core_web_lg",
                     f"xx_ent_wiki_sm"):
            if cand in spacy_models:
                spacy_model = cand
                break
        else:
            spacy_model = spacy_models[0]

    # --- Ontology / aliases / products ------------------------------------
    aliases, products = ([], [])
    if fetched:
        aliases, products = _ontology_from_page(page_text, brand)

    # --- Search intent -----------------------------------------------------
    search_intent = _score_intent(page_text) if page_text else "informational"
    # publishing/news brands are editorial by nature — 'subscribe now' etc.
    # in the footer must not flip them to transactional/commercial
    if has_news or " news" in brand.lower():
        search_intent = "informational"

    # --- Local services + harvester choice --------------------------------
    services = _local_services(scan)
    searxng_live = services.get("searxng")
    ollama_live = services.get("ollama")
    harvester = "searxng" if searxng_live else "duckduckgo"

    # --- Engine matrix -----------------------------------------------------
    low_text = (page_text or "").lower()
    engines = list(DEFAULT_ENGINE_MATRIX)
    if any(k in low_text for k in ("youtube", "video", "watch now")):
        engines.append("YouTube Search")
    if has_news or "news" in low_text[:4000]:
        engines.append("Google News")
    if any(k in low_text for k in ("reddit", "forum", "community")):
        engines.append("Reddit Search")
    if any(k in low_text for k in ("app store", "google play", "ios app",
                                   "android app")):
        engines.append("App Store Search")
    engines = _dedupe(engines, limit=9)

    # --- Entity weighting + ontology alias lines --------------------------
    ew_lines: List[str] = [f"{brand}|1.5"]
    if products:
        ew_lines.append(f"{brand}|{', '.join(a.split(brand + ' ', 1)[-1] for a in aliases)}")
    for c in competitors[:4]:
        ew_lines.append(f"{c}|1.0")
    for prod in products[:4]:
        full = f"{brand} {prod}"
        ew_lines.append(f"{full}|1.2")

    # --- Query templates (intent-aware, all six intents) --------------------
    # Entity proximity shifts by intent: informational vs transactional vs
    # comparison vs local vs navigational vs commercial. Emit the full
    # enterprise set so vectors are evaluated in context, never in a vacuum.
    qt = [
        "informational|what is {topic}",
        "informational|{topic} explained",
        "informational|how {brand} does {topic}",
        "comparison|{brand} vs alternatives",
        "comparison|{brand} vs {topic} leaders",
        "commercial|best {topic} options",
        "commercial|{brand} features and pricing",
        "transactional|best {topic} for {brand}",
        "transactional|{brand} {topic} pricing",
        "navigational|{brand} official site",
        "local|{topic} near me",
        "research|{topic} guide",
    ]
    if search_intent == "transactional":
        qt += ["transactional|buy {topic} from {brand}",
               "transactional|{brand} {topic} free trial"]
    elif search_intent == "commercial":
        qt += ["commercial|top rated {topic} 2026",
               "commercial|{brand} reviews vs competitors"]
    elif search_intent == "local":
        qt += ["local|{brand} locations", "local|{brand} near me"]
    elif search_intent == "navigational":
        qt += ["navigational|{brand} app download",
               "navigational|{brand} login"]

    # --- SERP footprints / content feeds ----------------------------------
    # Deep-research grade: verified Wikipedia + up to 6 same-site deep links as
    # per-engine footprints; feeds include declared RSS + sitemap + conventional
    # feed guesses verified against fetched scan results.
    page_links = _extract_links(page_html, final_url or base_url) if page_html else []
    footprints: List[str] = []
    wiki_url = _wikipedia_url(brand) if _remaining() > 4 else None
    # only emit fetchable footprints when a real homepage was fetched
    if (final_url or url) and "." in _domain(final_url or url or ""):
        footprints = _build_footprints(final_url or url or base_url,
                                       page_links, wiki_url)

    feeds = feeds or []
    # verify conventional feed guesses against the scan bundle before adding
    for guess in (_absolutize("/feed", final_url or base_url),
                  _absolutize("/rss.xml", final_url or base_url),
                  _absolutize("/blog/feed", final_url or base_url)):
        if guess and guess not in feeds and scan.get(guess):
            feeds.append(guess)
    feeds = _dedupe(feeds, limit=8)
    news_sitemap = None
    if has_news and sitemap_url and "news" in (sitemap_url.lower() or ""):
        news_sitemap = sitemap_url

    # --- Numbers / knobs ---------------------------------------------------
    # Deep-research grade: scale synthetic queries, top-k and thresholds from
    # live evidence (topic count, competitor count, entity density, multilingual).
    synthetic_query_count = min(30, max(14, len(topics) * 2 + len(competitors)))
    top_k = min(10, max(5, 3 + len(topics) // 2))
    # observed entity density from the page
    density = 0.015
    if page_text:
        org_hits = len(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b",
                                  page_text))
        words = len(re.split(r"\s+", page_text))
        if words > 200:
            density = max(0.008, min(0.03, round(org_hits / words, 3)))
    hrt = 0.75 if density >= 0.022 else (0.65 if density <= 0.012 else 0.70)
    chunk_tokens = 384 if multilingual else 512

    # --- Assemble the pre-fill dict ----------------------------------------
    result: Dict[str, Any] = {
        "target_brand": brand,
        "industry_topics": "".join(t + "\n" for t in topics[:12]).rstrip("\n"),
        "competitor_entities": "".join(c + "\n" for c in competitors[:8]).rstrip("\n"),
        "crawl_depth": str(_crawl_depth(doc_count, has_news, len(page_text), 50)),
        "harvester": harvester,
        "prefer_searxng": bool(searxng_live),
        "auto_threshold": True,
        "high_relevance_threshold": f"{hrt:.2f}",
        "search_intent": search_intent,
        "spacy_model": spacy_model,
        "embedding_model": embedding_model,
        "engine_matrix": ", ".join(engines),
        "entity_weighting": "".join(l + "\n" for l in ew_lines).rstrip("\n"),
        "query_templates": "".join(l + "\n" for l in qt).rstrip("\n"),
        "serp_footprints": "".join(l + "\n" for l in footprints).rstrip("\n"),
        "synthetic_query_count": str(synthetic_query_count),
        "chunk_tokens": str(chunk_tokens),
        "chunk_overlap_tokens": "64",
        "target_entity_density": f"{density:.3f}",
        "top_k_retrieval": str(top_k),
    }
    if locality:
        result["locality"] = locality
    if searxng_live:
        result["searxng_base_url"] = searxng_live
    if ollama_live:
        result["ollama_base_url"] = ollama_live
        result["ollama_model"] = "llama3"
    # leave genuine feeds; if only a generic sitemap exists, prefer it over
    # nothing only when we actually discovered a sitemap URL on the wire
    if feeds:
        result["content_feeds"] = "".join(u + "\n" for u in feeds).rstrip("\n")
    elif news_sitemap:
        result["content_feeds"] = news_sitemap
    if products:
        # ontology aliases ride in the entity_weighting field (weight+alias
        # lines) but expose them separately too for the UI / future fields.
        result["ontology_aliases"] = "".join(
            f"{brand}|{a.split(brand + ' ', 1)[-1]}\n" for a in aliases
        ).rstrip("\n")

    fields_filled = sorted(f"{k}" for k in result if not k.startswith("_"))
    result["_meta"] = {
        "source_url": url or None,
        "final_url": final_url or None,
        "requested": input_text,
        "title": (fetched or {}).get("title") if fetched else None,
        "domain": dom or _domain(base_url),
        "language": lang,
        "multilingual": multilingual,
        "sitemap_urls": doc_count,
        "searxng_live": bool(searxng_live),
        "ollama_live": bool(ollama_live),
        "locality_source": ("site" if locality and fetched else
                            ("search" if locality else "none")),
        "fields_filled": fields_filled,
        "competitors_incomplete": competitors_incomplete,
        "note": (
            "Live site analysis + web search used to pre-fill every field. "
            "Review before running."
            if fetched else
            "Could not fetch the URL live; brand name used directly and web "
            "search enriched the fields."
        ),
        "cannot_derive": [
            "corpus_dir", "corpus_files",
        ],
    }
    return result