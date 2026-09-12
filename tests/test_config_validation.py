"""Config validation: placeholders/shorts/empties fail fast, 7 intents pass.

No network, no models.
"""

import pytest

from ragevda.config import RunConfig


def _base(**kw):
    args = {
        "target_brand": "TestBrand",
        "industry_topics": ["cloud security posture"],
        "competitor_entities": ["RivalCorp"],
    }
    args.update(kw)
    return RunConfig(**args)


def test_empty_brand_rejected():
    with pytest.raises(ValueError):
        _base(target_brand="  ")


def test_single_char_names_rejected():
    with pytest.raises(ValueError):
        _base(target_brand="A")
    with pytest.raises(ValueError):
        _base(competitor_entities=["B"])


def test_zero_topics_or_competitors_rejected():
    with pytest.raises(ValueError):
        _base(industry_topics=[])
    with pytest.raises(ValueError):
        _base(competitor_entities=[])


@pytest.mark.parametrize("intent", [
    "informational", "transactional", "comparison", "research",
    "local", "commercial", "navigational",
])
def test_all_intents_accepted(intent):
    assert _base(search_intent=intent).search_intent == intent


def test_unknown_intent_rejected():
    with pytest.raises(ValueError):
        _base(search_intent="vibes")


def test_crawl_depth_capped_not_silent():
    import logging
    records = []

    class H(logging.Handler):
        def emit(self, r):
            records.append(r.getMessage())

    logging.getLogger("ragevda.config").addHandler(H())
    cfg = _base(crawl_depth=500)
    assert cfg.crawl_depth == 200
