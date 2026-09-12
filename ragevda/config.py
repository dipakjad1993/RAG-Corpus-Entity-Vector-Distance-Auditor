"""Run configuration schema, validation, and loader.

The configuration is intentionally plain-data so that it can be supplied as
a YAML / JSON file or constructed programmatically.  It captures every input
described in the product brief:

* Target brand name
* 3-10 target industry topics / seed concepts
* 2-5 competitor entities
* Crawl depth (number of results / pages per query)
* Optional locality / geo target
* Pluggable harvester + model choices and analysis knobs

Enterprise / advanced inputs (added for the full product):
* Search intent & query templates (informational / transactional / organic)
* Ontology mapping (sub-brands / product modules / patents aliased to an entity)
* Competitor content change logs (RSS / sitemap feeds for real-time ingestion)
* RAG chunking & contextual-window controls (token windows, overlap)
* Target embedding model + the AI "engine matrix" each score is measured against
* Semantic-drift time-series database (for cross-run drift tracking)
* Optional local LLM (Ollama) gap-analysis engine
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

import yaml

from .utils import get_logger

logger = get_logger("ragevda.config")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_SPACY_MODEL = "en_core_web_sm"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# Minimum characters required for brand/topic/competitor names to prevent
# accidentally trivial inputs (e.g. "a", "AI", single letters).
_MIN_NAME_LEN = 2
# Maximum allowed number of industry topics (prevents combinatorial explosion
# in query expansion and SoV matrix).
_MAX_TOPICS = 20
# Maximum allowed number of competitor entities.
_MAX_COMPETITORS = 15

# The AI "engine matrix" -- the answer engines + search interfaces whose RAG
# retrieval behaviour we model. Scores are reported per engine so teams can
# compare Vector Share of Voice across the surfaces that actually matter.
DEFAULT_ENGINE_MATRIX = [
    "Google AI Overviews",
    "SearchGPT",
    "Gemini",
    "Perplexity",
    "Bing Copilot",
]

# Query-intent templates applied to each topic. Each intent captures a
# different retrieval surface (informational / transactional / local / qa).
DEFAULT_QUERY_TEMPLATES = {
    "informational": "what is {topic}",
    "transactional": "best {topic} software tools",
    "comparison": "{topic} vs alternatives comparison",
    "research": "how to {topic} guide",
    "commercial": "top {topic} solutions compared",
    "navigational": "{brand} {topic} official site",
    "local": "{topic} near me {brand}",
}

# RAG contextual-window defaults (tokens). Most retrieval back-ends index
# 256-512 token chunks; we simulate these windows before scoring so cosine
# similarity reflects what a real retriever sees rather than a whole-article
# vector (which creates false positives).
DEFAULT_CHUNK_TOKENS = 512
DEFAULT_CHUNK_OVERLAP_TOKENS = 64


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class RunConfig:
    # --- Required inputs ---------------------------------------------------
    target_brand: str
    industry_topics: List[str] = field(default_factory=list)
    competitor_entities: List[str] = field(default_factory=list)

    # --- Harvesting --------------------------------------------------------
    crawl_depth: int = 50
    locality: Optional[str] = None
    harvester: str = "duckduckgo"          # duckduckgo | searxng | file
    prefer_searxng: bool = False           # if True and searxng_base_url set, SearXNG is primary
    searxng_base_url: Optional[str] = None
    corpus_dir: Optional[str] = None       # used when harvester == "file"
    corpus_files: List[str] = field(default_factory=list)
    include_reddit: bool = True
    include_news: bool = True
    request_timeout: int = 20
    max_concurrency: int = 8
    user_agent: str = DEFAULT_USER_AGENT
    proxy: Optional[str] = None

    # --- NLP / models ------------------------------------------------------
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    spacy_model: str = DEFAULT_SPACY_MODEL
    min_paragraph_chars: int = 40
    sentence_chunk_chars: int = 400         # chunk long text for embedding

    # --- Analysis ----------------------------------------------------------
    top_n_recommendations: int = 25
    max_search_queries: int = 120           # bounds live search calls (no limit on topics/comps)
    max_pages: int = 200                    # max web pages fetched (0 = unlimited)
    auto_threshold: bool = True             # auto-calibrate high-relevance per topic
    high_relevance_threshold: float = 0.70  # used only when auto_threshold=False
    tight_binding_threshold: float = 0.75   # competitor "tightly bound"
    far_threshold: float = 0.50             # brand "far" from topic
    confidence_min_support: int = 3          # min entity mentions for "high" confidence

    # --- Output ------------------------------------------------------------
    output_dir: str = "./ragevda_output"
    random_seed: int = 42

    # --- Data integrity / verification -----------------------------------
    # If True (default), the audit aborts loudly instead of silently emitting
    # degraded TF-IDF/regex numbers when the real ML models cannot load. This
    # is what keeps every report "verified" rather than accidentally fake.
    require_real_models: bool = True
    # Optional alias strings per entity, e.g. {"Cricinfo": ["cricinfo.com",
    # "ESPNCricinfo"]}. These are matched in addition to the exact name so a
    # brand is not wrongly scored as "omitted" when the page says it differently.
    entity_aliases: Dict[str, List[str]] = field(default_factory=dict)
    # Optional owned/known domains per entity, e.g. {"Cricinfo": ["cricinfo.com"]}.
    # A document on that domain is treated as a genuine mention of the entity.
    entity_domains: Dict[str, List[str]] = field(default_factory=dict)
    # Custom entity weighting: relative importance of each entity's proximity in
    # the report (e.g. value the brand at 1.5x a competitor). Keys are canonical
    # entity names (brand or competitor), values are positive float weights.
    entity_weighting: Dict[str, float] = field(default_factory=dict)
    # Drop exact + near-duplicate harvested documents so counts are not inflated.
    dedupe_near: bool = True
    near_dup_threshold: float = 0.95

    # --- Advanced / enterprise inputs (Section 2 extended) -----------------
    # Search intent: which retrieval surface to optimise for. Drives the
    # query-template expansions (informational / transactional / comparison /
    # research / local).
    search_intent: str = "informational"
    # Custom query templates per intent, e.g. {"transactional": "buy {topic}"}.
    # ``{topic}`` and ``{brand}`` are substituted. Keys beyond the defaults
    # define additional intents.
    query_templates: Dict[str, str] = field(default_factory=dict)
    # Ontology mapping: sub-brands / product modules / patent names that the
    # engine should treat as owned by an entity. Keyed by canonical entity
    # (brand or competitor), values are the alias strings. These merge into
    # the entity-alias mention map so a sub-brand mention counts.
    ontology_aliases: Dict[str, List[str]] = field(default_factory=dict)
    # Competitor / industry content change logs (RSS or sitemap URLs). When
    # present the harvester ingests newly-published articles directly, giving
    # real-time freshness on top of the searched corpus.
    content_feeds: List[str] = field(default_factory=list)
    # Search-engine scraping footprints: concrete source URLs per AI-engine
    # surface (e.g. specific Google AI Overview / Bing Copilot citations or
    # Perplexity source links) to ingest separately instead of one blended SERP.
    # Each entry may be a bare URL or "engine|label|url" to tag its source.
    serp_footprints: List[str] = field(default_factory=list)
    # RAG chunking / contextual-window simulator (tokens).
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS
    chunk_overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS
    # Token-density target: fraction of a RAG window the brand should occupy
    # to displace a competitor chunk from top-k retrieval.
    target_entity_density: float = 0.015
    top_k_retrieval: int = 5
    # The AI engine matrix to score Vector Share of Voice against.
    engine_matrix: List[str] = field(default_factory=lambda: list(DEFAULT_ENGINE_MATRIX))
    # Semantic-drift time-series database depth (historical runs retained).
    drift_history_keep: int = 60
    # Optional local LLM (Ollama) for gap analysis / chunk summarisation.
    ollama_base_url: Optional[str] = None     # e.g. http://localhost:11434
    ollama_model: str = "llama3"
    use_llm: bool = True                      # use Ollama when available
    # Number of synthetic retrieval queries to reverse-engineer.
    synthetic_query_count: int = 12

    # -----------------------------------------------------------------------
    def __post_init__(self) -> None:
        self.validate()

    # -----------------------------------------------------------------------
    def validate(self) -> None:
        if not self.target_brand or not self.target_brand.strip():
            raise ValueError("target_brand must be a non-empty string")
        brand = self.target_brand.strip()
        if len(brand) < _MIN_NAME_LEN:
            raise ValueError(
                f"target_brand must be at least {_MIN_NAME_LEN} characters "
                f"(got {len(brand)}: {brand!r}). Use your real brand name, "
                "not a placeholder."
            )

        topics = [t.strip() for t in self.industry_topics if t and t.strip()]
        if len(topics) < 1:
            raise ValueError(
                "Provide at least one industry topic. These are the real "
                "topics/keywords your brand competes for in AI search."
            )
        if len(topics) > _MAX_TOPICS:
            raise ValueError(
                f"Too many industry topics ({len(topics)}; max {_MAX_TOPICS}). "
                "Reduce to avoid combinatorial explosion in query expansion."
            )
        for t in topics:
            if len(t) < _MIN_NAME_LEN:
                raise ValueError(
                    f"Industry topic {t!r} is too short (min {_MIN_NAME_LEN} "
                    "chars). Use descriptive topic phrases, not single words."
                )
        self.industry_topics = topics

        comps = [c.strip() for c in self.competitor_entities if c and c.strip()]
        if len(comps) < 1:
            raise ValueError(
                "Provide at least one competitor entity. These are the real "
                "companies/brands you compete against in AI search results."
            )
        if len(comps) > _MAX_COMPETITORS:
            raise ValueError(
                f"Too many competitors ({len(comps)}; max {_MAX_COMPETITORS}). "
                "Focus on your top direct competitors."
            )
        for c in comps:
            if len(c) < _MIN_NAME_LEN:
                raise ValueError(
                    f"Competitor {c!r} is too short (min {_MIN_NAME_LEN} "
                    "chars). Use real company/brand names."
                )
        self.competitor_entities = comps

        if self.crawl_depth < 1:
            raise ValueError("crawl_depth must be >= 1")
        if self.crawl_depth > 200:
            # hard safety cap to avoid abusive scraping
            self.crawl_depth = 200

        if self.harvester not in ("duckduckgo", "searxng", "file"):
            raise ValueError("harvester must be duckduckgo | searxng | file")

        # "Prefer SearXNG" toggle: make SearXNG the primary live harvester
        # whenever a URL is configured, falling back to DuckDuckGo otherwise.
        if self.prefer_searxng and self.searxng_base_url and self.harvester == "duckduckgo":
            self.harvester = "searxng"

        if self.harvester == "searxng" and not self.searxng_base_url:
            raise ValueError("searxng_base_url is required when harvester=searxng")

        if self.harvester == "file":
            if not self.corpus_dir and not self.corpus_files:
                raise ValueError(
                    "corpus_dir or corpus_files is required when harvester=file"
                )

        for name in ("high_relevance_threshold", "tight_binding_threshold",
                      "far_threshold"):
            val = getattr(self, name)
            if not 0.0 <= val <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

        if not 0.0 <= self.near_dup_threshold <= 1.0:
            raise ValueError("near_dup_threshold must be in [0, 1]")

        if self.chunk_tokens < 64:
            raise ValueError("chunk_tokens must be >= 64")
        if not 0 <= self.chunk_overlap_tokens < self.chunk_tokens:
            raise ValueError("chunk_overlap_tokens must be in [0, chunk_tokens)")
        if not 0.0 <= self.target_entity_density <= 1.0:
            raise ValueError("target_entity_density must be in [0, 1]")
        if self.top_k_retrieval < 1:
            raise ValueError("top_k_retrieval must be >= 1")
        if self.search_intent not in ("informational", "transactional",
                                       "comparison", "research", "local",
                                       "commercial", "navigational") \
                and self.search_intent not in self.query_templates:
            raise ValueError(
                "search_intent must be a known intent (informational / "
                "transactional / comparison / research / local / commercial / "
                "navigational) or a key of query_templates")

        # Warn (not fail) on malformed topic/competitor strings that look
        # accidentally split -- typically unbalanced parentheses from a
        # copy/paste typo. They still run, but produce lower-quality topic
        # embeddings, so we surface it loudly instead of hiding it.
        for bad in list(self.industry_topics) + list(self.competitor_entities):
            if bad.count("(") != bad.count(")"):
                logger.warning(
                    "Malformed entity/topic (unbalanced parentheses): %r -- "
                    "this is usually a config typo and degrades embedding "
                    "quality. Fix the parentheses before trusting the output.",
                    bad,
                )

        # Warn on suspiciously generic names that often come from placeholder
        # configs rather than real brand analysis.
        _GENERIC_NAMES = {
            "acme", "widget", "corp", "company", "enterprise", "software",
            "product", "brand", "business", "inc", "llc", "ltd", "group",
            "test", "demo", "example", "placeholder", "smoke", "fake",
            "compa", "compb", "alpha", "beta",
        }
        all_names = [brand.lower()] + [c.lower() for c in self.competitor_entities]
        for name in all_names:
            if name in _GENERIC_NAMES:
                logger.warning(
                    "Name %r looks like a placeholder/generic. Use real "
                    "brand/company names for accurate analysis results.", name
                )

    # -----------------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            if path.endswith(".json"):
                json.dump(self.to_dict(), fh, indent=2)
            else:
                yaml.safe_dump(self.to_dict(), fh, sort_keys=False)

    # -----------------------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "RunConfig":
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with open(path, "r", encoding="utf-8") as fh:
            if path.endswith((".yaml", ".yml")):
                data = yaml.safe_load(fh)
            elif path.endswith(".json"):
                data = json.load(fh)
            else:
                raise ValueError("Config must be .yaml/.yml or .json")
        if not isinstance(data, dict):
            raise ValueError("Config root must be a mapping")
        return cls(**data)

    # -----------------------------------------------------------------------
    def all_entities(self) -> List[str]:
        """Every brand-like entity the analysis cares about (brand + competitors)."""
        return [self.target_brand] + self.competitor_entities

    def entity_alias_map(self) -> Dict[str, List[str]]:
        """Alias / sub-brand strings per entity (original-case keys).

        Merges the explicit ``entity_aliases`` with the ontology mapping
        ``ontology_aliases`` (sub-brands / product modules / patent names
        owned by an entity), lowercased + de-duped. This is what lets a
        sub-brand mention count toward its parent brand so a page is not
        wrongly scored as "omitted" just because it used a product name.
        """
        out: Dict[str, List[str]] = {}
        for e in self.all_entities():
            seen: Dict[str, None] = {}
            al: List[str] = []
            for source in (self.entity_aliases, self.ontology_aliases):
                for a in source.get(e, []) or []:
                    a = a.strip().lower()
                    if a and a not in seen and a != e.lower():
                        seen[a] = None
                        al.append(a)
            out[e] = al
        return out

    def all_aliases_for(self, entity: str) -> List[str]:
        """Every alias (incl. sub-brands) owned by an entity, original-case."""
        return list(self.entity_alias_map().get(entity, []))

    def entity_domain_map(self) -> Dict[str, List[str]]:
        """Owned/known domains per entity (original-case keys), lowercased."""
        out: Dict[str, List[str]] = {}
        for e in self.all_entities():
            seen: Dict[str, None] = {}
            doms: List[str] = []
            for d in self.entity_domains.get(e, []) or []:
                d = d.strip().lower()
                d = d[1:] if d.startswith(".") else d
                if d and d not in seen:
                    seen[d] = None
                    doms.append(d)
            out[e] = doms
        return out

    def query_templates_for(self, intent: str) -> Dict[str, str]:
        """Resolve the query templates active for a given intent.

        Returns ``{intent_label: template}``. Custom ``query_templates`` always
        override the defaults, so a user can toggle transactional vs
        informational vs comparison retrieval surfaces per run.
        """
        merged = dict(DEFAULT_QUERY_TEMPLATES)
        merged.update(self.query_templates or {})
        if intent in merged:
            return {intent: merged[intent]}
        # fall back to the default intent family and surface everything
        return dict(merged)

    def _apply_template(self, template: str, topic: str, brand: str) -> str:
        try:
            return template.format(topic=topic, brand=brand)
        except (KeyError, IndexError):
            return template

    def search_queries(self, intents: Optional[List[str]] = None) -> List[str]:
        """Expand topics into concrete search queries.

        Priority order guarantees every topic gets its **primary** query even
        when ``max_search_queries`` caps the total (so no topic is silently
        dropped from the live search). The expansions are:

          1. The raw topic query (always first, one per topic)
          2. Intent-template queries for the active intent(s) -- informational /
             transactional / comparison / research surfaces have different
             retrieval mixes, so vectors are evaluated in context, not a vacuum.
          3. Topic + brand mention intent (co-citation pages)
          4. Each brand sub-brand / ontology alias as a query
          5. Topic + Reddit (if enabled)
          6. Topic + News (if enabled)
          7. Topic + each competitor

        There is **no limit** on how many topics or competitors you may supply;
        only the number of outbound search calls is bounded.
        """
        base: List[str] = []
        brand = self.target_brand
        topics = list(self.industry_topics)
        # 1) primary topic queries (keep first so all topics are covered)
        base += topics
        # 2) intent-template queries (query templates per active intent)
        active_intents = intents or [self.search_intent]
        templates = {}
        for it in active_intents:
            templates.update(self.query_templates_for(it))
        for topic in topics:
            for tpl in templates.values():
                q = self._apply_template(tpl, topic, brand)
                if q and q.strip():
                    base.append(q.strip())
        # 3) topic + brand
        for topic in topics:
            base.append(f"{topic} {brand}")
        # 4) sub-brands / ontology aliases owned by the brand
        for alias in self.entity_alias_map().get(brand, []):
            base.append(f"{alias} {brand} product suite")
        # 5) topic + reddit
        if self.include_reddit:
            base += [f"{topic} reddit" for topic in topics]
        # 6) topic + news
        if self.include_news:
            base += [f"{topic} news" for topic in topics]
        # 7) topic + competitor
        for topic in topics:
            for comp in self.competitor_entities:
                base.append(f"{topic} {comp}")
        # de-duplicate while preserving order
        seen, ordered = set(), []
        for q in base:
            if q.lower() not in seen:
                seen.add(q.lower())
                ordered.append(q)
        # bound the number of outbound search calls
        cap = getattr(self, "max_search_queries", 120)
        if cap and len(ordered) > cap:
            ordered = ordered[:cap]
        return ordered

    def drift_db_path(self) -> str:
        """Path to the persistent semantic-drift time-series database.

        Lives inside the run output dir so every audit's cross-run history is
        stored next to its reports (same ``web_output/jobs`` convention used by
        History & Trends)."""
        import os
        return os.path.join(self.output_dir, "drift_timeseries.duckdb")
