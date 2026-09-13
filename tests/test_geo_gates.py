"""Harvester chain, drift stats, poisoning, eval gates, llms, prompts, security."""
from ragevda.config import RunConfig
from ragevda.analysis.drift import _linear_trend, _zscore, _two_tailed_p, forecast_next

import pytest

pytestmark = pytest.mark.geo


def _cfg(**kw):
    args = {"target_brand": "TestBrand", "industry_topics": ["cloud security"],
            "competitor_entities": ["RivalCorp"]}
    args.update(kw)
    return RunConfig(**args)


def test_paid_search_fail_open_without_keys():
    from ragevda.harvester.paid_search import brave_search, tavily_search, exa_search
    assert brave_search("q", "", 3) == []
    assert tavily_search("q", "", 3) == []
    assert exa_search("q", "", 3) == []


def test_answers_off_by_default():
    from ragevda.harvester.answers import harvest_answers
    assert harvest_answers([{"prompt": "x"}], _cfg()) == []


def test_ugc_respects_toggles():
    from ragevda.harvester import ugc
    cfg = _cfg()
    cfg.ugc_reddit = cfg.ugc_youtube = cfg.ugc_tiktok = False
    assert ugc.harvest_reddit(["q"], cfg) == []
    assert ugc.harvest_youtube(["q"], cfg) == []
    assert ugc.harvest_tiktok(["q"], cfg) == []


def test_drift_stats_real():
    assert _linear_trend([1.0, 2.0, 3.0]) > 0
    assert _linear_trend([3.0, 2.0, 1.0]) < 0
    assert _linear_trend([1.0]) == 0.0
    assert abs(_zscore(10.0, [1.0, 1.2, 0.9, 1.1])) > 2
    p = _two_tailed_p(1.96)
    assert 0.04 < p < 0.06
    assert forecast_next([1.0, 2.0, 3.0]) is not None
    assert forecast_next([1.0]) is None


def test_eval_gates_shape():
    from ragevda.eval.gates import run_eval_gates
    cfg = _cfg()
    report = {"meta": {"context_stats": {"doc_count": 4}},
              "proximity": {"rows": [{"entity": "TestBrand", "proximity": 0.9}]},
              "invisibility": {"per_topic": [{"topic": "cloud security",
                                              "vector_share_of_voice_pct": 50}]},
              "advanced": {"poisoning": {}, "chunking": {"retrieved_count": 1,
                                                          "window_count": 4}}}
    out = run_eval_gates(report, cfg)
    assert set(out["metrics"]) == {"faithfulness", "answer_relevancy",
                                   "context_precision", "context_recall"}
    assert isinstance(out["gate_pass"], bool)


def test_llms_outputs_write(tmp_path):
    from ragevda.reporting.llms import write_llms_outputs
    cfg = _cfg()
    report = {"meta": {"version": "x", "verification_score": 90},
              "provenance": [], "recommendations": [], "advanced": {}}
    paths = write_llms_outputs(str(tmp_path), report, cfg)
    assert "llms.txt" in paths and "mcp.json" in paths
    assert (tmp_path / "llms.txt").read_text().startswith("# TestBrand")


def test_prompt_library_expands():
    from ragevda.prompt_library import build_prompts
    cfg = _cfg(prompt_volume=1)
    cfg.prompt_frames = ["informational"]
    cfg.personas = ["default"]
    out = build_prompts(cfg)
    assert out and all("prompt" in p for p in out)


def test_security_ssrf_blocks_private():
    from ragevda.utils import assert_url_allowed
    with pytest.raises(ValueError):
        assert_url_allowed("http://127.0.0.1/admin")
    with pytest.raises(ValueError):
        assert_url_allowed("ftp://example.com/x")
    with pytest.raises(ValueError):
        assert_url_allowed("https://evil.com", allowlist=["example.com"])


def test_pydantic_adapter_rejects_garbage():
    from ragevda.config_schema import validate_dict
    with pytest.raises(ValueError):
        validate_dict({"target_brand": "x", "industry_topics": [],
                       "competitor_entities": ["RivalCorp"]})
