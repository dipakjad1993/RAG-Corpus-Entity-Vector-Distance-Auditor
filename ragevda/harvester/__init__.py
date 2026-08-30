"""Harvester factory + package exports."""

from __future__ import annotations

from .base import Document, Harvester, new_document, domain_of
from .duckduckgo import DuckDuckGoHarvester
from .searxng import SearXNGHarvester
from .file_reader import FileHarvester
from .feeds import FeedHarvester

__all__ = [
    "Document", "Harvester", "new_document", "domain_of",
    "DuckDuckGoHarvester", "SearXNGHarvester", "FileHarvester",
    "FeedHarvester", "build_harvester",
]


def build_harvester(config):
    """Return the configured harvester instance."""
    kind = getattr(config, "harvester", "duckduckgo")
    if kind == "duckduckgo":
        return DuckDuckGoHarvester(config)
    if kind == "searxng":
        return SearXNGHarvester(config)
    if kind == "file":
        return FileHarvester(config)
    raise ValueError(f"unknown harvester: {kind}")
