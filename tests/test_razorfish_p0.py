"""Razorfish P0/P1 review lock-in: DON'T-TOUCH defaults + new engines.

No network, no models. Guards the 2026 positioning:
nomic FULL default / MiniLM LITE-only, hybrid+reranker, multi harvesters,
UGC Reddit+YouTube core / TikTok opt-in, require_real_models, 6 standard
intents, 10-engine matrix, volatility + verdict + robots + EVAL v2.
"""


def _cfg(**kw):
    from ragevda.config import RunConfig
    base = {"target_brand": "GuardianReal",
            "industry_topics": ["digital journalism"],
            "competitor_entities": ["NYTimesReal"]}
    base.update(kw)
    return RunConfig(**base)


def test_dont_touch_defaults():
    from ragevda.config import (DEFAULT_EMBEDDING_MODEL, LEGACY_EMBEDDING_MODEL,
                                STANDARD_INTENTS, DEFAULT_ENGINE_MATRIX)
    cfg = _cfg()
    assert DEFAULT_EMBEDDING_MODEL == "nomic-ai/nomic-embed-text-v1.5"
    assert cfg.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert LEGACY_EMBEDDING_MODEL == "sentence-transformers/all-MiniLM-L6-v2"
    assert cfg.harvester == "multi"
    assert cfg.answer_harvester == "multi"
    assert cfg.ugc_reddit is True and cfg.ugc_youtube is True
    assert cfg.ugc_tiktok is False
    assert cfg.require_real_models is True
    assert cfg.use_hybrid_retrieval is True
    assert "bge-reranker" in cfg.reranker_model
    assert set(STANDARD_INTENTS) == {"informational", "transactional",
                                     "comparison", "research", "local", "qa"}
    assert len(DEFAULT_ENGINE_MATRIX) == 10
    assert "Google AI Mode" in DEFAULT_ENGINE_MATRIX
    assert cfg.generate_llms_txt is False  # P2 hygiene, zero AIO effect


def test_lite_profile_uses_minilm():
    from ragevda.config import RunConfig
    lite = RunConfig.lite_profile("GuardianReal", ["digital journalism"], ["NYTimesReal"])
    assert "MiniLM" in lite.embedding_model
    assert lite.use_hybrid_retrieval is False
    full = RunConfig.full_profile("GuardianReal", ["digital journalism"], ["NYTimesReal"])
    assert "nomic" in full.embedding_model
    assert full.use_hybrid_retrieval is True


def test_volatility_single_sample_honest():
    from ragevda.analysis.volatility import volatility_report, summarize_repeats
    s = summarize_repeats([0.6])
    assert s["status"] == "SINGLE_SAMPLE" and s["n"] == 1
    v = volatility_report(None, {"per_topic": []}, 5)
    assert v["overall"]["status"] == "UNKNOWN"
    v2 = volatility_report({"q1": [0.5, 0.55, 0.52, 0.48, 0.51]}, {"per_topic": []}, 5)
    assert v2["overall"]["status"] in ("STABLE", "WATCH", "VOLATILE")
    assert v2["overall"]["prompts_with_repeats"] == 1


def test_volatility_decay_sort_and_alerts():
    from ragevda.analysis.volatility import volatility_report, decay_alerts
    drift = {"per_topic": [
        {"topic": "a", "sov_delta": -8.0, "proximity_delta": -0.06,
         "trend_sov_per_run": -1.0, "trend_proximity_per_run": -0.01,
         "data_points": 4, "has_prior": True},
        {"topic": "b", "sov_delta": 1.0, "proximity_delta": 0.01,
         "trend_sov_per_run": 0.2, "trend_proximity_per_run": 0.0,
         "data_points": 4, "has_prior": True}]}
    v = volatility_report({}, drift, 5)
    assert v["citation_decay"][0]["topic"] == "a"
    assert decay_alerts(v, 5.0)[0]["topic"] == "a"


def test_exec_verdict_card():
    from ragevda.reporting.verdict import compute_exec_verdict
    rep = {"advanced": {"visibility": {
        "table": [{"entity": "GuardianReal", "visibility": 62.0, "position": 1,
                   "mentions": 100, "citations_linked": 30, "mention_share_pct": 40.0},
                  {"entity": "NYTimesReal", "visibility": 55.0, "position": 2,
                   "mentions": 80, "citations_linked": 20, "mention_share_pct": 30.0}],
        "brand_visibility": 62.0, "brand_position": 1,
        "competitor_median_visibility": 55.0, "delta_vs_median": 7.0},
        "eeat": {"avg_score": 70}, "drift": {"alerts": []}},
        "invisibility": {"composite_invisibility_index_pct": 20.0,
                         "composite_vector_share_of_voice_pct": 45.0}}
    vd = compute_exec_verdict(rep, "GuardianReal")
    assert vd["visibility"] == 62.0 and vd["position"] == 1
    assert vd["delta_vs_median"] == 7.0
    assert "lead" in vd["sentence"].lower() or "GuardianReal" in vd["sentence"]
    assert vd["tone"] == "good"


def test_robots_fail_open():
    from ragevda.harvester.robots import allowed, filter_urls
    assert allowed("not a url") is True
    assert allowed("https://example.com/page") in (True, False)  # network-dependent, never raises
    ok, blocked = filter_urls(["https://example.com/a", "notaurl"])
    assert len(ok) + len(blocked) == 2


def test_eval_v2_protocol():
    from ragevda.eval.v2_protocol import precision_recall, load_labels
    labels = load_labels("ragevda/eval/labels_v2.sample.json")
    assert len(labels) == 5
    res = precision_recall(labels)
    assert res["n"] == 5 and 0.0 <= res["macro_f1"] <= 1.0
    assert set(res["per_class"]) == {"linked", "unlinked", "omitted"}


def test_dashboard_renders_verdict_and_volatility():
    from ragevda.reporting.dashboard import render_dashboard
    data = {
        "meta": {"config": {"target_brand": "GuardianReal",
                            "industry_topics": ["digital journalism"],
                            "competitor_entities": ["NYTimesReal"],
                            "confidence_min_support": 3, "max_pages": 200,
                            "top_k_retrieval": 5},
                 "context_stats": {"doc_count": 4},
                 "embedding_kind": "sentence-transformers",
                 "harvest_stats": {}, "data_integrity": {},
                 "verification_score": 80, "verified": True},
        "proximity": {"rows": []},
        "citation_gap": {"entity_summary": [],
                         "off_page_targets": [],
                         "rag_invisibility_index": 20.0},
        "invisibility": {"per_topic": [],
                         "composite_invisibility_index_pct": 20.0,
                         "composite_vector_share_of_voice_pct": 45.0},
        "recommendations": [], "provenance": [],
        "advanced": {"visibility": {
            "table": [{"entity": "GuardianReal", "visibility": 50.0,
                       "position": 1, "mentions": 10, "citations_linked": 4,
                       "mention_share_pct": 50.0}],
            "brand_visibility": 50.0, "brand_position": 1,
            "competitor_median_visibility": 40.0, "delta_vs_median": 10.0,
            "method": "m"},
            "volatility": {"overall": {"status": "STABLE", "mean_stdev": 0.03,
                                       "prompts_with_repeats": 2,
                                       "prompts_tracked": 3, "answer_repeats": 5,
                                       "note": "ok"},
                           "citation_decay": [], "method": "m"},
            "eeat": {"rows": [], "avg_score": 70, "critical_count": 0},
            "crawler": {"configured": False},
            "attribution_gsc": {"configured": False, "note": "set creds"},
            "attribution_ga4": {"configured": False, "note": "set prop"}},
    }
    html = render_dashboard(data)
    assert "TL;DR" in html
    assert "Volatility" in html
    assert "Visibility Score" in html
