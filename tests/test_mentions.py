"""Mention detection: aliases map to parents, boundaries respected.

No network, no models (pure-regex path only).
"""

from ragevda.nlp.ner import NER


def test_alias_attribution():
    pats, amap = NER.build_mention_patterns(
        ["TestBrand", "RivalCorp"],
        {"TestBrand": ["tb pro", "testbrand enterprise"]},
    )
    counts = NER.find_mentions(
        "TestBrand rules. TB PRO wins again. RivalCorp lags.", pats, amap)
    assert counts["TestBrand"] == 2
    assert counts["RivalCorp"] == 1


def test_word_boundaries():
    pats, amap = NER.build_mention_patterns(["Apple"], {})
    counts = NER.find_mentions("Pineapple smoothies, apples aplenty.", pats, amap)
    assert counts.get("Apple", 0) == 0
    counts2 = NER.find_mentions("Apple releases iPhone.", pats, amap)
    assert counts2["Apple"] == 1


def test_case_insensitive():
    pats, amap = NER.build_mention_patterns(["Guardian"], {})
    counts = NER.find_mentions("the GUARDIAN reported.", pats, amap)
    assert counts["Guardian"] == 1
