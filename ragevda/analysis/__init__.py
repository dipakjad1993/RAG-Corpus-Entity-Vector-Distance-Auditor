"""Analysis package exports."""

from __future__ import annotations

from .context import build_context, AnalysisContext, EntityStats
from .proximity import analyze_proximity
from .citation_gap import analyze_citation_gap
from .invisibility import analyze_invisibility
from .recommendations import generate as generate_recommendations
from .advanced import run_advanced

__all__ = [
    "build_context", "AnalysisContext", "EntityStats",
    "analyze_proximity", "analyze_citation_gap", "analyze_invisibility",
    "generate_recommendations", "run_advanced",
]
