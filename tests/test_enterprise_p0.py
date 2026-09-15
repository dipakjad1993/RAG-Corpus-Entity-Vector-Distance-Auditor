"""P0 enterprise modules: real-data unit tests (no network, no models)."""
from types import SimpleNamespace

import numpy as np


def _doc(url="https://example.com/a", title="Example guide", text="The Guardian is defined as a news platform that publishes journalism. It costs $5.", **kw):
    d = {"url": url, "title": title, "text": text, "source_type": kw.get("source_type", "web"),
         "domain": "example.com", "doc_id": url, "final_url": url, "http_status": 200}
    d.update(kw)
    return SimpleNamespace(**d)


def test_rrf_merge_orders_corroborated_first():
    from ragevda.harvester.paid_search import _rrf_merge, multi_search_all
    a = [("https://x/1", "t1", "s1"), ("https://x/2", "t2", "s2")]
    b = [("https://x/2", "t2", "s2"), ("https://x/3", "t3", "s3")]
    merged = _rrf_merge([a, b])
    assert merged[0][0] == "https://x/2"  # in both lists -> first
    assert multi_search_all([], SimpleNamespace()) == []


def test_citation_reverse_thresholds():
    from ragevda.analysis.citation_reverse import reverse_citations

    class E:
        def embed(self, texts):
            # answer vec [1,0]; passage vecs vary
            out = []
            for t in texts:
                out.append(np.array([1.0, 0.0]) if len(t) < 500 else np.array([1.0, 0.0]))
            return out
    docs = [_doc(text="word " * 200)]
    res = reverse_citations(["answer text about the topic"], docs, E())
    assert "steals" in res and isinstance(res["steals"], list)


def test_eeat_gate_critical_on_empty():
    from ragevda.analysis.eeat_gate import eeat_gate
    res = eeat_gate([_doc(text="hello world")])
    assert res["rows"][0]["verdict"] == "CRITICAL"
    assert res["avg_score"] < 50


def test_entity_gain_flags_missing_definition():
    from ragevda.analysis.entity_gain import score_corpus
    res = score_corpus([_doc(text="plain words here " * 50)], {}, "AcmeReal")
    assert res["rows"][0]["score"] < 100
    assert any("definition" in f.lower() or "200 words" in f for f in res["rows"][0]["fixes"])


def test_fanout_coverage_shape():
    from ragevda.analysis.fanout_exec import fanout_coverage
    cfg = SimpleNamespace(target_brand="AcmeReal", entity_domains={})
    res = fanout_coverage(["best crm"], [_doc(url="https://acmereal.com/x", text="AcmeReal crm guide explained")], cfg, n=4)
    assert res["avg_coverage_pct"] >= 0
    assert len(res["clusters"][0]["slices"]) == 4


def test_reddit_topics_groups_by_subreddit():
    from ragevda.analysis.reddit_topics import reddit_topics
    d = _doc(url="https://old.reddit.com/r/tech/comments/x", title="tech thread")
    res = reddit_topics([d])
    assert res["subreddits"][0]["subreddit"] == "tech"


def test_media_multilingual_white_label():
    from ragevda.analysis.media_checks import media_checks
    from ragevda.nlp.multilingual import multilingual_report, detect_lang
    from ragevda.reporting.white_label import white_label_header, mcp_tools_status
    docs = [_doc()]
    m = media_checks(docs, ["crm software"])
    assert "summary" in m
    assert detect_lang("the quick brown fox and the lazy dog for the win") == "en"
    ml = multilingual_report(docs, SimpleNamespace(languages=["en"], geo_variants=["US"]))
    assert ml["lang_counts"]
    cfg = SimpleNamespace(target_brand="B", mcp_tools=["get_pricing"], agency_name="")
    assert "brand" in white_label_header(cfg)
    assert "get_pricing" in mcp_tools_status(cfg, docs)["tools"]


def test_tracking_volumes_and_alert():
    from ragevda.tracking import prompt_volume_weights, drift_alert
    w = prompt_volume_weights([{"text": "a", "volume": 3}, {"text": "b", "volume": 1}])
    assert abs(sum(w.values()) - 1.0) < 1e-6
    assert drift_alert({"invisibility": {"composite_vector_share_of_voice_pct": 50.0}}, 40.0)["alert"] is True


def test_defaults_multi_and_intents():
    from ragevda.config import RunConfig, STANDARD_INTENTS
    cfg = RunConfig(target_brand="GuardianReal", industry_topics=["digital journalism"],
                    competitor_entities=["NYTimesReal"])
    assert cfg.harvester == "multi"
    assert cfg.answer_harvester == "multi"
    assert set(STANDARD_INTENTS) == {"informational", "transactional", "comparison", "research", "local", "qa"}
    assert cfg.generate_llms_txt is False
    assert cfg.ugc_tiktok is False


def test_probe_infer_and_deep_sections():
    from ragevda.analysis.probe_infer import infer_intent, infer_entities
    from ragevda.reporting.deep_sections import md_citation_steals, md_fanout, md_eeat_gain, md_media_multilingual
    intent, conf, _ = infer_intent("pricing plans buy now checkout")
    assert intent == "transactional"
    assert infer_entities(["Guardian Newsroom"], []) != []
    rep = {"advanced": {"citation_reverse": {"steals": []}, "fanout_coverage": {"clusters": [], "avg_coverage_pct": 0},
                        "eeat": {"avg_score": 10, "critical_count": 1, "pass_rate_pct": 0},
                        "entity_gain": {"avg_score": 5, "rows": []},
                        "media": {"summary": {}, "recommendations": [], "rows": []},
                        "multilingual": {"lang_counts": {}, "geo_variants": [], "gaps": []}}}
    assert "Citation" in md_citation_steals(rep)
    assert "Fan-out" in md_fanout(rep)
    assert "E-E-A-T" in md_eeat_gain(rep)
    assert "Media" in md_media_multilingual(rep)
