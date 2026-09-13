"""Regression: orchestrator paid-API branch must use cleaner.extract_text.

The v2.0.0 multi-harvester branch once imported a non-existent
``clean_html`` symbol, crashing every live audit at harvest time with
``ImportError: cannot import name 'clean_html'``. This test pins the real
cleaner API (no network, no models).
"""
import pathlib


def test_cleaner_api_exists():
    from ragevda.harvester.cleaner import extract_text, clean_document
    html = ("<html><head><title>T</title></head><body><nav>menu</nav>"
            "<article><p>Game Rant covers video game news and reviews.</p></article>"
            "</body></html>")
    text = extract_text(html, url="https://example.com/x")
    assert "video game news" in text
    assert "menu" not in text
    doc = clean_document("https://example.com/x", html, "T", "web", "q")
    assert doc.text and doc.domain == "example.com"


def test_orchestrator_uses_real_cleaner_symbol():
    src = pathlib.Path("ragevda/orchestrator.py").read_text(encoding="utf-8")
    assert "clean_html" not in src
    assert "extract_text" in src


def test_version_matches_release():
    from ragevda import __version__
    from ragevda.version import __version__ as v2
    assert __version__ == v2 == "2.0.0"
