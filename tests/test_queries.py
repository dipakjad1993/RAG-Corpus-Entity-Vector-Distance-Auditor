"""Query expansion: every topic keeps its primary query under the cap.

No network, no models.
"""

from ragevda.config import RunConfig


def _cfg(**kw):
    args = {
        "target_brand": "TestBrand",
        "industry_topics": ["cloud security", "zero trust networking", "soc automation"],
        "competitor_entities": ["RivalA", "RivalB"],
        "max_search_queries": 9,
    }
    args.update(kw)
    return RunConfig(**args)


def test_primary_queries_survive_cap():
    cfg = _cfg()
    qs = cfg.search_queries()
    assert len(qs) <= 9
    for t in cfg.industry_topics:
        assert t in qs, f"primary topic query dropped: {t!r}"


def test_dedup_order_preserving():
    cfg = _cfg(max_search_queries=120)
    qs = cfg.search_queries()
    assert len(qs) == len({q.lower() for q in qs})


def test_brand_topic_coverage():
    cfg = _cfg(max_search_queries=120)
    qs = cfg.search_queries()
    assert any("TestBrand" in q for q in qs)
    assert any("reddit" in q for q in qs)
