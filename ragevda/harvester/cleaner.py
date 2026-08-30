"""HTML cleanroom parsing.

We isolate the pure, indexable body text that a RAG crawler actually ingests
by using `trafilatura` (which is purpose-built for this) with `beautifulsoup4`
as a robust fallback.  Boilerplate (headers, footers, nav, sidebars, ads) is
discarded so that embeddings and NER reflect genuine article content.
"""

from __future__ import annotations

import logging
from typing import Optional

from .base import Document, new_document
from ..utils import normalize_text, get_logger

logger = get_logger("ragevda.cleaner")


def extract_text(html: str, url: str = "", title_hint: str = "") -> str:
    """Return cleaned body text from raw HTML, or '' if extraction fails."""
    if not html:
        return ""
    text: Optional[str] = None
    try:
        import trafilatura

        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("trafilatura failed for %s: %s", url, exc)

    if not text or len(text.strip()) < 50:
        # fallback to BeautifulSoup readability-ish extraction
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "noscript", "header",
                             "footer", "nav", "aside", "form", "svg"]):
                tag.decompose()
            # prefer <article> / <main> if present
            main = soup.find("article") or soup.find("main") or soup.body
            if main:
                text = main.get_text(separator=" ")
        except Exception as exc:  # noqa: BLE001
            logger.warning("bs4 fallback failed for %s: %s", url, exc)

    return normalize_text(text or "")


def clean_document(url: str, html: str, title: str, source_type: str,
                   query: str, metadata: Optional[dict] = None) -> Document:
    text = extract_text(html, url=url)
    return new_document(
        url=url,
        title=title,
        source_type=source_type,
        query=query,
        text=text,
        raw_html=html,
        metadata=metadata,
    )
