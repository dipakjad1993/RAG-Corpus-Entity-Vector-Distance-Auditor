"""Probe entity hygiene: camelCase splits, generic nouns rejected, rivals kept.

No network, no models.
"""

from ragevda.analysis.auto_probe import _clean_entity_name, _sanitize_entities


def test_camelcase_split():
    assert _clean_entity_name("EmeraldPublishing") == "Emerald Publishing"


def test_generic_nouns_rejected():
    out = _sanitize_entities(["Funding", "Subscribe", "Live Blog", "Vox Media"],
                             "TestBrand")
    assert "Funding" not in out
    assert "Vox Media" in out


def test_distinctive_multiword_kept():
    out = _sanitize_entities(["News UK", "KM Media Group", "Financial Times"],
                             "TestBrand")
    assert out == ["News UK", "KM Media Group", "Financial Times"]


def test_brand_never_competitor():
    out = _sanitize_entities(["TestBrand", "TestBrand Pro"], "TestBrand")
    assert out == []


def test_brand_stem_overlap_rejected():
    out = _sanitize_entities(["Guardian News", "Discover The Guardian",
                              "Media's", "Telegraph Media Group"],
                             "Theguardian")
    assert "Guardian News" not in out
    assert "Discover The Guardian" not in out
    assert "Media's" not in out
    assert "Telegraph Media Group" in out
