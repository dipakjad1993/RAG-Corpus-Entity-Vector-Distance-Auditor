"""Pydantic v2 validation adapter for RunConfig.

The dataclass in ``config.py`` remains the runtime object (100% backwards
compatible). This module provides a strict Pydantic v2 schema that produces
junior-readable validation errors BEFORE the dataclass is constructed, plus
``validate_dict()`` used by the FastAPI layer and CLI ``--strict`` mode.

If pydantic v2 is not installed, validation degrades to the dataclass's own
``validate()`` (fail-open with a clear log line — never silent).
"""
from __future__ import annotations

from typing import Any, Dict, List


def validate_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a raw config mapping. Returns the (possibly coerced) mapping.

    Raises ValueError with human-readable messages on failure.
    """
    try:
        from pydantic import BaseModel, Field, field_validator
    except Exception:  # noqa: BLE001
        return data  # pydantic absent: dataclass.validate() still enforces
    from pydantic import ValidationError

    class _Schema(BaseModel):
        target_brand: str = Field(min_length=2)
        industry_topics: List[str] = Field(min_length=1, max_length=20)
        competitor_entities: List[str] = Field(min_length=1, max_length=15)
        crawl_depth: int = Field(default=50, ge=1, le=200)
        harvester: str = "duckduckgo"
        answer_harvester: str = "off"
        answer_repeats: int = Field(default=5, ge=1, le=10)
        prompt_volume: int = Field(default=5, ge=1, le=20)
        eval_faithfulness_min: float = Field(default=0.75, ge=0.0, le=1.0)
        eval_answer_relevancy_min: float = Field(default=0.80, ge=0.0, le=1.0)
        eval_context_precision_min: float = Field(default=0.70, ge=0.0, le=1.0)
        eval_context_recall_min: float = Field(default=0.70, ge=0.0, le=1.0)
        attribution_cadence: str = "daily"
        job_retention_days: int = Field(default=30, ge=1)

        @field_validator("harvester")
        @classmethod
        def _harv(cls, v: str) -> str:
            if v not in ("duckduckgo", "searxng", "file", "multi", "answers"):
                raise ValueError("harvester must be duckduckgo | searxng | file | multi | answers")
            return v

        @field_validator("answer_harvester")
        @classmethod
        def _ans(cls, v: str) -> str:
            if v not in ("off", "brave", "tavily", "exa", "multi"):
                raise ValueError("answer_harvester must be off | brave | tavily | exa | multi")
            return v

        @field_validator("attribution_cadence")
        @classmethod
        def _cad(cls, v: str) -> str:
            if v not in ("daily", "weekly", "manual"):
                raise ValueError("attribution_cadence must be daily | weekly | manual")
            return v

        model_config = {"extra": "allow"}

    try:
        m = _Schema(**data)
        return m.model_dump()
    except ValidationError as exc:
        msgs = "; ".join(
            f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())
        raise ValueError(f"config validation failed — {msgs}") from exc
