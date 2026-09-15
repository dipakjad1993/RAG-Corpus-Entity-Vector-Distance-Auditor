"""Caps: max_pages / max_search_queries (0 = unlimited)."""
import pytest


def _cfg(**kw):
    from ragevda.config import RunConfig
    base = dict(target_brand="TestBrand",
                industry_topics=["analytics software"],
                competitor_entities=["RivalOne"])
    base.update(kw)
    return RunConfig(**base)


def test_zero_means_unlimited_ok():
    c = _cfg(max_pages=0, max_search_queries=0)
    assert c.max_pages == 0
    assert c.max_search_queries == 0


def test_negative_caps_rejected():
    with pytest.raises(ValueError):
        _cfg(max_pages=-1)
    with pytest.raises(ValueError):
        _cfg(max_search_queries=-5)


def test_search_queries_uncapped_with_zero():
    topics = [f"topic number {i}" for i in range(20)]  # max allowed topics
    comps = ["RivalOne", "RivalTwo"]
    capped = _cfg(industry_topics=topics, competitor_entities=comps,
                  max_search_queries=120).search_queries()
    free = _cfg(industry_topics=topics, competitor_entities=comps,
                max_search_queries=0).search_queries()
    assert len(free) > 120
    assert len(capped) == 120


def test_schedule_profile_carries_caps():
    from ragevda.scheduler import Schedule
    s = Schedule(id="x", name="n", brand="TestBrand", topics=["analytics software"],
                 competitors=["RivalOne"], max_pages=0, max_search_queries=0)
    p = s.profile()
    assert p["max_pages"] == 0
    assert p["max_search_queries"] == 0
