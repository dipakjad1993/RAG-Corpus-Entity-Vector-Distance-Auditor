# RAG-EVDA — RAG Corpus Entity & Vector Distance Auditor

![CI](https://github.com/dipakjad1993/RAG-Corpus-Entity-Vector-Distance-Auditor/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![Local-only](https://img.shields.io/badge/LLM-100%25%20local-orange)
![Version](https://img.shields.io/badge/version-2.2.0-black)
[![Live demo](https://img.shields.io/badge/demo-live%20on%20Render-brightgreen)](https://rag-corpus-entity-vector-distance-auditor.onrender.com/)

> **Try it live:** https://rag-corpus-entity-vector-distance-auditor.onrender.com/
> (full enterprise UI — 11 inputs, Auto-Detect, Deep Analysis, Outputs hub).

> **A zero-cost, fully-local intelligence engine that decodes how modern AI search
> engines (ChatGPT, Gemini, Claude, Perplexity, Copilot, Grok, Meta AI, DeepSeek,
> Google AI Overviews, Google AI Mode) semantically perceive a brand relative
> to its competitors inside a retrieval-augmented generation (RAG) corpus —
> and tells you exactly what to publish to change that perception.**

**RAG-EVDA** crawls the exact web pages, forums, and articles that are currently
defining your industry niche, processes them through **100% local** NLP models,
and computes your brand's **exact semantic distance** from core topics and
competitors — with **zero OpenAI / Ahrefs / Semrush / BrightEdge API keys** and
**zero data leaving your machine**.

| | | |
|---|---|---|
|  **125 docs** audited in the reference Guardian run |  **$0** API cost, forever |  **Full output bundle** per run (JSON + HTML + DuckDBs + brief + action plan + WebMCP + Looker) |

### What's new in v2.2.0 — Enterprise GEO-depth release

- **Real multi-query paid fan-out** — `multi_search_all()` fans out over ALL
  queries (ThreadPool batch, RRF-merged, `RAGEVDA_FANOUT_QUERIES=20` cap) with
  concurrent fetching. Previously only `queries[0]` reached Brave/Tavily/Exa.
- **Sane GEO defaults** — `harvester: multi` + `answer_harvester: multi` out of
  the box (DDG is fallback-only); standard intent set
  (`informational/transactional/comparison/research/local/qa`,
  `commercial`/`navigational` legacy-only); TikTok demoted to opt-in plugin
  (`ugc_tiktok: false`, Reddit + YouTube stay core); `generate_llms_txt: false`
  (P2 hygiene — zero AIO effect per Google May-2026).
- **10 new P0 analysis engines** (all real-data, fail-open, in `advanced`):
  passage-BERT citation stealer (`citation_reverse`, >0.88 steal), fan-out
  coverage map (`fanout_coverage`), E-E-A-T gate (`eeat`, <50 CRITICAL),
  entity-density + Information Gain scorer (`entity_gain`, 15+ entities/page),
  subreddit topic extractor (`reddit_topics`), image/video/Merchant/GBP checks
  (`media`), per-doc language + geo-variant report (`multilingual`),
  white-label header + corpus-evidenced MCP tools, prompt-volume weighting +
  daily snapshots + drift alerts (`tracking`), probe-inference split
  (`probe_infer`) + deep-analysis sections (`deep_sections`).
- **Race-safe scheduler** — due-set snapshot under lock, callback outside the
  lock, mutations re-applied under lock; 10-engine matrix + nomic defaults.
- **Docs + version safety** — `docs/EMBEDDINGS.md` (nomic default + latency
  table), `docs/SERVING.md` (FastAPI-only enterprise path), `docs/SCOPE_2026.md`
  (what was demoted and why), CI `version-check` (README == version.py ==
  pyproject). Full suite: **59 passed, 9 skipped**.

### What's new in v2.1.1 — Audit-always-completes release

- **No more "stuck at X%"** — every pipeline phase now logs a named marker
  (harvest plan → UGC → dedupe → corpus built → context → proximity →
  citation-gap → invisibility → recommendations → advanced → freshness →
  persist → CSV → dashboard) and the web progress bar maps each one to a
  monotonic 6→98% stage, so the full 10-engine run is always visible.
- **45s heartbeat watchdog** — silent CPU/network stretches (large embedding
  batches, the one-time ~600MB sentiment-model download, rate-limited
  harvests) emit `still working: <stage> (<elapsed>s)` so the console and bar
  prove liveness instead of freezing.
- **Harvest time-box** — `RAGEVDA_HARVEST_TIMEOUT` (default 480s): the DDG
  harvester stops issuing new queries on deadline and continues with the
  candidates already collected; the fetch phase honors 2× deadline and keeps
  partial results. Empty-query fallbacks cut from 3 variants to 1.
- **UGC time-box** — `RAGEVDA_UGC_TIMEOUT` (default 90s), 5 seed queries per
  source (reddit/youtube/tiktok degrade gracefully on budget exhaustion).
- **Faster by default on slow networks** — fewer dead-end round-trips, earlier
  progress signal (`harvest plan: N queries x depth D` at 8%), per-10-page
  fetch heartbeats, and actionable deadline warnings in the log.

### What's new in v2.1.0 — LITE + Visibility + Closed-loop release

- **Render LITE profile (fixes "hit its memory limit")** — new
  `Dockerfile.render` + `requirements.render.txt` + `render.yaml`: CPU-only
  torch, MiniLM-90MB embeddings, reranker OFF, hybrid OFF, lazy reportlab /
  webapp imports, 1 worker × 2 threads, `/health` that never loads models.
  Boot ~180–250MB, audit ~380–450MB — fits the 512MB free tier and any
  phone/laptop. Full power stays for paid/local via `RunConfig.full_profile()`
  (see `RunConfig.lite_profile()` / `apply_env_overrides()`).
- **10-engine daily-tracking matrix** — AI Overviews, AI Mode, ChatGPT,
  Gemini, Claude, Perplexity, Copilot, Grok, Meta AI, DeepSeek. Default path
  for real GEO is documented: `harvester: multi` + `answer_harvester: multi` +
  `answer_repeats: 5–10` with Brave/Tavily/Exa keys via env.
- **C-suite Visibility Score** (`analysis/visibility.py`) — Visibility 0–100,
  Position rank, Mentions vs linked-Citations split, and brand delta vs the
  competitor median (Semrush-style), all from real report evidence.
- **Query fan-out + volume weighting** (`analysis/fanout.py`) — template ×
  frames × personas expansion with PAA + observed-title prompts, every prompt
  traffic-weighted for forward tracking.
- **Citation-source analytics** (`analysis/citation_funnel.py`) — cited-vs-found
  funnel per entity, fan-out decomposition by query family, and an outreach
  list with contact-page guesses.
- **Persona × platform sentiment + word association**
  (`analysis/sentiment_matrix.py`) — the CMO narrative layer over the
  transformer auditor.
- **FactCheck auto-correction loop** (`eval/factcheck.py`) — eval gates now
  attach concrete rewrite/schema/sourcing fixes per finding instead of only
  failing the build.
- **Closed-loop execution** (`reporting/action_plan.py`) — every run emits
  `action_plan.json` + `action_plan.md` + `wp_drafts/` (question-H2 stubs,
  refresh list, Reddit actions, outreach, WordPress-ready Markdown).
- **WebMCP-first agent surface** — `.well-known/webmcp.json` + `mcp.json` +
  `agent.json` (Chrome 149 `navigator.modelContext`); `llms.txt` kept lean
  for coding agents only (zero ranking/AIO effect per Google 2026).
- **Wired attribution** — GSC Generative-AI impressions pull (service-account
  JSON; AI Mode queries via the regular Performance report), GA4 Data API
  LLM-referral split (chatgpt/perplexity/gemini/claude), Slack webhook
  alerts; `configured: false` without creds, never synthesised.
- **AI-crawler analytics** (`analysis/crawler.py`) — GPTBot / OAI-SearchBot /
  ClaudeBot / PerplexityBot frequency from access logs (`AI_CRAWLER_LOG`).
- **Looker Studio bundle** (`reporting/looker.py`) — `looker_connector.json` +
  stdlib-csv `looker_rows.csv` (no pandas, LITE-safe).
- **Responsive + deeper brief** — single-column bento <768px, lazy-chart CSS,
  system-font fallback; `rag_content_brief.md` now appends visibility,
  funnel/outreach, FactCheck fixes, fan-out and word-association sections.

### What's new in v2.0.0 — Enterprise GEO release

- **Live LLM Answer Harvester (P0)** — queries real answer surfaces
  (`answer_harvester: brave | tavily | exa | multi`, `answer_repeats: 5–10`)
  per prompt, parses citations + answer text into `source_type='answer'`
  documents. Without this, no tool is a GEO tool.
- **First-class UGC corpus** — `harvester/ugc.py` (Reddit search JSON,
  YouTube transcripts, TikTok SERP) runs on every audit; earned media is
  ~80–90% of AI answers, so invisibility no longer lies by ignoring it.
- **Paid search primaries** — `harvester/paid_search.py` (Brave / Tavily / Exa,
  keys via env). DDG HTML scraping is demoted to **fallback-only** and logged
  as such. New `harvester: "multi"` fans out SearXNG + paid APIs → DDG.
- **Modern embeddings default** — `nomic-ai/nomic-embed-text-v1.5` (137M,
  CPU-fast, Apache-2.0, 8k ctx); BGE-M3 / Qwen3-Embedding-0.6B when cached;
  MiniLM last-resort only. Model-aware tokenizers (no hardcoded MiniLM),
  SQLite embedding cache keyed by `sha1(model+chunk)`.
- **Hybrid retrieval** — `ragevda/nlp/hybrid.py`: BM25 + dense cosine (RRF
  fusion) + `bge-reranker-v2-m3` cross-encoder rerank (fail-open). Cosine-only
  retrieval is gone.
- **Vector index** — `ragevda/nlp/vector_index.py` (FAISS `IndexFlatIP` when
  installed, NumPy brute-force otherwise); engine authority scan fixed from
  O(N²) to O(1); NER patterns built once and reused.
- **Unified semantic chunking** — one sentence-aware BPE packer shared by
  embeddings and density (`utils.chunk_text` delegates to
  `token_windows`); the double-chunking bug (char 400/40 vs BPE 512/64
  measuring different windows) is fixed. Silent `char/4` fallback now raises
  under `require_real_models=True`.
- **Prompt library + personas** — `ragevda/prompts.yaml` + `prompt_library.py`:
  informational/transactional/comparison/local/qa frames × personas ×
  geo-variants × `prompt_volume` repeats (forward-tracks real prompts, not
  just reverse-engineered synthetic queries).
- **llms.txt + MCP** — every run emits `llms.txt`, `llms-full.txt`,
  `agent.json`, `.well-known/mcp.json` (get_pricing/check_stock,
  Lighthouse-13.3-ready) from real report data.
- **RAGAS-style eval gates** — `ragevda/eval/gates.py` (faithfulness ≥0.75,
  answer relevancy ≥0.80, context precision/recall ≥0.70); `pytest --geo`
  fails the build on gate failure.
- **E-E-A-T factuality** — ghost-citation tracking (brand cited but unnamed)
  + Information Gain scoring (depth/structured/data/stats/citations).
- **GSC + GA4 attribution** — `ragevda/attribution.py` (Gen-AI impressions,
  chatgpt/perplexity/claude channel split, SKU tracking); explicit
  `configured: false` when unconfigured — never synthesised.
- **Enterprise serving** — FastAPI async service (`ragevda/api.py`: `/health`,
  `/jobs`, OpenAPI, OTEL hook), persistent SQLite job queue (no more
  single-flight rejection, `RAGEVDA_WORKERS` pool), API-key auth, per-IP rate
  limiting, CSRF double-submit, SSRF guard on every fetch, non-root Docker,
  loopback bind by default. Flask UI split into `web_templates/` + `static/`.
- **Config enterprise fields + Pydantic v2** — `config_schema.py` adapter with
  junior-readable errors; 20+ new validated keys (answer/UGC/eval/attribution/
  jobs/security). Drift adds ETS-lite forecast + Slack webhook alerts.
- **Consolidated outputs** — `reporting/report_writer.py` 5-output contract
  (`report.json`, `dashboard.html`, DuckDBs, `rag_content_brief.md`,
  llms.txt patch); legacy CSVs archived under `_legacy/`.
- **Build** — hatchling + `uv` (`uv sync`, `uv.lock`), `requirements.txt`
  kept as a thin pip-compat shim; 48 tests incl. `--geo` gates.
- **Stats fix** — `_two_tailed_p` corrected (was multiplying by √2π instead
  of dividing; z=1.96 now yields p≈0.05, covered by test).

### What's new in v1.3.0 — Enterprise experience release

- **Enterprise 2026 web UI** — gradient hero with live detection stats, bento
  input grid for all 11 fields, clickable 3-step flow
  (Inputs → Deep Analysis → Outputs), sticky run bar with an explicit
  ** Show Outputs** action, skeleton loaders, toasts, and percent/elapsed
  progress with color-coded live logs. Pixel-first type
  (`Google Sans` → bundled Roboto Flex) with a fully working dark/light toggle.
- **Deep-research Auto-Detect** — paste any brand or URL and the tool performs
  live multi-source reconnaissance (homepage + robots/sitemap/about/services/
  blog/news, JSON-LD, live topic/competitor/HQ searches, Wikipedia check) and
  pre-fills **all 11 enterprise inputs** with verified real-time data.
- **Issue highlighting everywhere** — every engine is scanned for real computed
  problems and surfaced as bold **CRITICAL / HIGH RISK / WATCH / STRENGTH**
  cards: a global summary on Step 2, per-engine banners on all 10 deep-dive
  pages, and red/amber/green flagged rows in every key table.
- **Enterprise PDF** (`report.pdf`, ~17 pages) — cover page with KPI cards,
  captioned charts, per-section tinted issue callouts, color-coded metric
  cells, the complete analysis of all 10 engines, and the full outputs ledger.
  Stale cached PDFs self-heal: the server rebuilds any PDF older than the
  generator on next download.
- **Outputs hub (Step 3)** — 12-section verified report with executive verdict,
  competitive leaderboard, full proximity/citation/off-page/action tables,
  and all 15 deliverable downloads.

### Try it in 30 seconds (offline, no network)

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m ragevda.cli run -c examples/offline_demo/config.yaml
# → opens ./ragevda_output_offline_demo/dashboard.html (10 sample docs, real local models)
```

### Architecture

```mermaid
flowchart LR
    CFG[Config / CLI / Web UI / FastAPI] --> H[Harvester<br/>multi: SearXNG · Brave/Tavily/Exa · UGC · answers<br/>DDG fallback-only · RSS · file]
    H --> NLP[Embeddings + NER<br/>nomic / BGE-M3 / Qwen3 · hybrid BM25+rerank<br/>spaCy + GLiNER · FAISS index · embed cache]
    NLP --> BRAIN[Analysis brain<br/>proximity · gaps · ghost cites · SoV · density · sentiment · drift+forecast · eval gates]
    BRAIN --> OUT[(DuckDB + report.json + HTML + brief + llms.txt/MCP)]
```

### Why not a black-box visibility SaaS?

| | RAG-EVDA | Profound / Peec / Otterly-style SaaS | Semrush / Ahrefs |
|---|---|---|---|
| Cost | $0 local | ~$99–999/mo | ~$139–499/mo |
| Data leaves machine | Never | Yes (black-box score) | Yes |
| Metric | Auditable vector math (proximity / invisibility / token-displacement) | Proprietary score | Ranks / backlinks |
| Provenance | Full DuckDB + hashes + latencies, reproducible offline | Not inspectable | Vendor trust |

Every number in the reports is **real, verifiable, and enterprise-grade**:
- real harvested documents with real URLs, content hashes, and fetch latencies
- real sentence-transformer embeddings (nomic default; BGE-M3 / Qwen3 / MiniLM-fallback)
- real spaCy named-entity recognition (multilingual + GLiNER ontology when available)
- real transformer sentiment (multilingual web-tone model + LLM-judge)
- real BPE token counting and per-window density math
- real regression-trend and z-score drift detection from your own run history

This document is a complete reference: **vision, installation, every input, every
core feature and function, every output file, the enterprise/advanced analysis
modules, a real worked example from a live The Guardian audit, responsible-use
guidelines, and the project's About + tags.**

---

## Table of Contents

1. [Why it exists](#why-it-exists)
2. [What's new in v2.2.0](#whats-new-in-v220--enterprise-geo-depth-release)
3. [What's new in v2.1.1](#whats-new-in-v211--audit-always-completes-release)
3. [What's new in v2.1.0](#whats-new-in-v210--lite--visibility--closed-loop-release)
4. [What's new in v2.0.0](#whats-new-in-v200--enterprise-geo-release)
5. [What's new in v1.3.0](#whats-new-in-v130--enterprise-experience-release)
6. [What problem it solves](#what-problem-it-solves)
7. [Architecture — four local micro-engines](#architecture--four-local-micro-engines)
8. [Feature summary table](#feature-summary-table)
9. [Installation](#installation)
10. [Quick start](#quick-start)
    - [CLI](#cli)
    - [Web UI](#web-ui)
    - [Python API](#python-api)
11. [Inputs — every field explained](#inputs--every-field-explained)
    - [Core inputs](#core-inputs)
    - [Enterprise / advanced inputs](#enterprise--advanced-inputs)
12. [Core features & functions — deep dive](#core-features--functions--deep-dive)
   - [Feature A — Zero-cost headless web harvester](#feature-a--zero-cost-headless-web-harvester)
   - [Feature B — Local embeddings & semantic mapping](#feature-b--local-embeddings--semantic-mapping)
   - [Feature C — Local NER & knowledge graph](#feature-c--local-ner--knowledge-graph)
   - [Feature D — Unlinked-authority & citation-gap finder](#feature-d--unlinked-authority--citation-gap-finder)
   - [Enterprise module 1 — Data-integrity verification / anti-fabrication](#enterprise-module-1--data-integrity-verification--anti-fabrication)
   - [Enterprise module 2 — Real-time source freshness & liveness](#enterprise-module-2--real-time-source-freshness--liveness)
   - [Enterprise module 3 — Real ML sentiment (transformers)](#enterprise-module-3--real-ml-sentiment-transformers)
   - [Enterprise module 4 — Data-driven per-engine share of voice](#enterprise-module-4--data-driven-per-engine-share-of-voice)
   - [Enterprise module 5 — Real BPE token density & chunking](#enterprise-module-5--real-bpe-token-density--chunking)
   - [Enterprise module 6 — Statistical semantic-drift detection](#enterprise-module-6--statistical-semantic-drift-detection)
   - [Enterprise module 7 — Vector poisoning / negative-SEO detection](#enterprise-module-7--vector-poisoning--negative-seo-detection)
   - [Enterprise module 8 — Synthetic query reverse-engineering](#enterprise-module-8--synthetic-query-reverse-engineering)
   - [Enterprise module 9 — RAG content brief & JSON-LD patch](#enterprise-module-9--rag-content-brief--json-ld-patch)
   - [Enterprise module 10 — Local-LLM (Ollama) gap analysis](#enterprise-module-10--local-llm-ollama-gap-analysis)
   - [Enterprise module 11 — Concurrency, dedup, and resilience](#enterprise-module-11--concurrency-dedup-and-resilience)
13. [Key metrics — the vocabulary of the report](#key-metrics--the-vocabulary-of-the-report)
14. [Outputs — every file explained](#outputs--every-file-explained)
15. [Schema — the report.json contract](#schema--the-reportjson-contract)
16. [Real worked example — a live The Guardian audit](#real-worked-example--a-live-the-guardian-audit)
17. [Live screenshots — real output from the The Guardian audit](#live-screenshots--real-output-from-the-the-guardian-audit)
18. [DuckDB — the local vector database](#duckdb--the-local-vector-database)
19. [Recurring / scheduled audits & drift history](#recurring--scheduled-audits--drift-history)
20. [Configuration reference — full YAML](#configuration-reference--full-yaml)
21. [Extending toward the polyglot architecture](#extending-toward-the-polyglot-architecture)
22. [Troubleshooting](#troubleshooting)
23. [Responsible use](#responsible-use)
24. [About](#about)
25. [Changelog](#changelog)
26. [Tags](#tags)
27. [Roadmap](#roadmap)
28. [Author](#author)
29. [License](#license)

---

## Why it exists

AI search engines build **multidimensional vector spaces**. When you type a
question into Gemini, SearchGPT, Google AI Overviews, Perplexity, or Bing
Copilot, the model does not "look up" your website the way a 2016 crawler did.
Instead it:

1. **Embeds** your query into a high-dimensional vector,
2. **retrieves** the top-`k` chunks of the corpus whose vectors are closest to
   that query vector (RAG — retrieval-augmented generation),
3. **reads** those chunks and composes an answer from them.

**If your brand entity sits far from your core industry concepts in that vector
space, the AI model ignores you — no matter how many backlinks you have.**
Your brand simply never gets *retrieved*.

RAG-EVDA turns "AI SEO guessing" into **raw, actionable mathematics**. It tells
you, with numbers, exactly how far your brand entity is from each of your target
topics and each competitor, where you are **invisible** in the retrieval corpus,
and precisely what to publish (topic, co-mentions, token density, target
publication) to close the gap.

---

## What problem it solves

| Traditional SEO tool | Gap that AI search exposes | What RAG-EVDA does instead |
|----------------------|----------------------------|----------------------------|
| Backlink / rank tracking | AI engines don't rank a URL — they retrieve a *chunk* | Measures **semantic vector proximity** (0–1) to topics & competitors |
| Keyword difficulty | Keywords are proxies for *concepts* | Embeds the **concept**, not the keyword string |
| Content gap analysis | Measures missing *keywords*, not missing *entities* | Finds **entity co-citation** gaps and unlinked high-relevance authority |
| SERP position | There is no SERP in a generative answer | Renders a **Vector Share of Voice** matrix per AI engine |
| Link-count authority | Authority is now *retrieval propensity* | Computes on-page features that drive **retrieval** |
| One-off audit | AI perception changes over time | Persistent **drift time-series** + trend/z-score alerts |

---

## Architecture — four local micro-engines

```
                    [ Config / CLI / Web UI ]
                             |
        +--------------------+--------------------+
        |                                         |
  Feature A: Harvester                    Feature B/C: NLP
  (DuckDuckGo / SearXNG /                  (embeddings + NER +
   Feeds / Footprints / Files)               co-occurrence graph)
        |                                         |
        +--------------------+--------------------+
                             |
             Feature D: Analysis (proximity, citation gap,
             invisibility index, share of voice, token density,
             sentiment, poisoning, drift, recommendations)
                             |
        Storage (DuckDB) + Reporting (CSV / JSON / HTML / PDF)
```

| Layer | Module(s) | What it does |
|-------|-----------|--------------|
| **A. Zero-Cost Web Harvester** | `ragevda.harvester` | `multi` fan-out: SearXNG + Brave/Tavily/Exa APIs + first-class Reddit/YouTube/TikTok UGC + live LLM answer harvester; DDG HTML scrape fallback-only + `trafilatura` clean-room parsing → clean text |
| **B. Local Embedding & Semantic Mapping** | `ragevda.nlp.embedder`, `ragevda.nlp.vector_index`, `ragevda.nlp.hybrid` | Modern defaults (nomic-embed-text-v1.5 → BGE-M3 → Qwen3 → MiniLM fallback-only) + cosine similarity; FAISS ANN index + SQLite embed cache; hybrid BM25 + dense + `bge-reranker-v2-m3` rerank; model-aware BPE counting |
| **C. Local NER & Knowledge Graph** | `ragevda.nlp.ner`, `ragevda.nlp.cooccurrence` | spaCy entity extraction (`xx_ent_wiki_sm` multilingual fallback, GLiNER for product ontology when installed) + `networkx` co-occurrence graph |
| **D. Analysis (the brain)** | `ragevda.analysis` | proximity, citation gap, ghost citations, information gain, invisibility index, share of voice, token density, sentiment (multilingual + LLM-judge), poisoning, drift + forecast, eval gates, recommendations, synthetic + library prompts, freshness (Cache-Control/sitemap/CDX), engine matrix |
| **NLP augmentation** | `ragevda.nlp.llm` | optional local **Ollama** free-text rationale (never invents data) |
| **Storage** | `ragevda.storage` | DuckDB local vector DB ($0 forever) + `drift_timeseries.duckdb` |
| **Orchestration** | `ragevda.orchestrator`, `ragevda.cli`, `ragevda.scheduler` | pipeline runner, CLI, recurring audit scheduler |
| **Serving** | `ragevda.webapp`, `ragevda.api`, `ragevda.jobs_store`, `ragevda.security` | Flask UI (split `web_templates/` + `static/`) + FastAPI async API with persistent SQLite job queue, API-key auth, rate limiting, CSRF, SSRF guard |
| **Reporting** | `ragevda.reporting` | Full output bundle: `report.json` / HTML dashboard / DuckDBs / RAG brief + JSON-LD / action plan + `wp_drafts/` / `llms.txt` + `agent.json` + WebMCP manifests / Looker bundle (legacy CSVs archived) |

---

## Feature summary table

| # | Core feature | Real output it produces |
|---|--------------|--------------------------|
| 1 | Zero-cost multi-source harvesting | Documents with real URLs, hashes, latency, HTTP status, headers |
| 2 | Local sentence-transformer embeddings (nomic default, BGE-M3/Qwen3 ready) + embed cache | Semantic vector proximity scores (0–1) |
| 3 | Local spaCy NER + mention detection | Entity counts, citation gaps, co-occurrence |
| 4 | RAG Invisibility Index | % of high-relevance articles where the brand is absent |
| 5 | Vector Share of Voice matrix | Brand vs competitor % presence in the retrieval pool |
| 6 | Unlinked high-relevance authority finder | Concrete URLs/threads to pitch |
| 7 | Prioritized recommendations | "Pitch Publication X — they cited Competitor A N times" |
| 8 | Data-integrity / verification score | Honest 0–100 validation of provenance + models |
| 9 | Real-time source freshness & liveness | Live %, median age, stale detection from real headers |
| 10 | Real ML sentiment (multilingual transformers + LLM-judge) | Per-entity net sentiment, negative risk windows |
| 11 | Data-driven per-engine SoV | Emergent engine differences from real on-page features |
| 12 | Real BPE token-density adjuster | Exact token counts + displacement plan per window |
| 13 | Statistical drift detection | Trend slopes, z-scores, anomaly flags across runs |
| 14 | Vector poisoning / negative-SEO detection | Threat score, toxic co-citing sources |
| 15 | Synthetic query re-engineering | Retrieval prompts each engine likely issues |
| 16 | RAG content brief + JSON-LD patch | Ready-to-publish guidance + structured data |
| 17 | Persistent DuckDB storage | Re-runnable, queryable local vector DB |
| 18 | Recurring scheduled audits | Scheduled full audits writing normal reports |
| 19 | Local-LLM gap analysis (Ollama) | Free-text rationale built only from real audited metrics |
| 20 | Auto-fallback & resilience | Paid-API → SearXNG → DDG chain, real-model fallback, robots.txt + SSRF guard, never fake data |
| 21 | Live LLM answer harvester | Real answer-engine citations + answer text per prompt (GEO) |
| 22 | Core UGC corpus | Reddit + YouTube transcripts in every audit (TikTok opt-in plugin only) |
| 23 | Hybrid retrieval | BM25 + dense RRF fusion + cross-encoder rerank |
| 24 | Prompt library + personas | Forward-tracked real prompts (frames × personas × geo × volume) |
| 25 | llms.txt + MCP | Agent-discoverability files from real report data |
| 26 | RAGAS-style eval gates | Faithfulness / relevancy / precision / recall with build-failing thresholds |
| 27 | Ghost citations + Information Gain | Unnamed brand citations + originality scoring |
| 28 | GSC + GA4 attribution | Gen-AI impressions + AI-referral channel split |
| 29 | Enterprise serving | FastAPI async API, persistent job queue, auth, rate-limit, CSRF, OTEL |

---

## Installation

### Requirements

- **Python 3.10+**
- A local **Hugging Face** model cache for embeddings (see below)
- The **spaCy** `en_core_web_sm` model (`python -m spacy download en_core_web_sm`)
- Web UI + PDF export are included: `flask`, `transformers`/`huggingface_hub`/`tokenizers`,
  `reportlab` (all in `requirements.txt`, installed automatically)
- Optional: `pypdf` (in `requirements.txt`) — enables **PDF ground-truth ingestion**
  in `file` harvester mode alongside HTML/Markdown/TXT/XML
- Optional: a self-hosted **SearXNG** instance (for higher-volume live search)
- Optional: **Ollama** (for the local-LLM gap-analysis module)

### Steps

```bash
# 1. clone / get the folder, then create a venv
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

# 2. install dependencies (preferred: uv; pip shim also works)
uv sync
# ...or: pip install -r requirements.txt

# 3. download the default spaCy NER model
python -m spacy download en_core_web_sm

# 4. (optional but recommended) pre-cache the default embedding + sentiment
# models so the tool never needs the network at audit time
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5')"
python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification; AutoTokenizer.from_pretrained('tabularisai/multilingual-sentiment-analysis'); AutoModelForSequenceClassification.from_pretrained('tabularisai/multilingual-sentiment-analysis')"

# 5. verify
python -m ragevda.cli --version   # → ragevda 2.1.1

# 6. run the quality gates (unit + enterprise GEO gates)
python -m pytest tests/ --geo -q  # → 59 passed, 9 skipped
```

> **Resilience guarantee.** If you request an embedding or NER model that is not
> cached/installed locally, RAG-EVDA automatically falls back to the best
> **real, locally-available** model (e.g. `Qwen3` → cached `nomic`; requested
> `en_core_web_trf` → installed `xx_ent_wiki_sm` / `en_core_web_sm`) instead of
> crashing. The TF-IDF/hashing fallback is **explicit opt-in only**
> (`RAGEVDA_ALLOW_FALLBACK=1`) — it never silently degrades to synthetic
> numbers when you asked for real models; the run fails loudly and honestly
> if *no* real model exists at all.

---

## Quick start

### CLI

```bash
# generate a starter config (interactive prompts for real inputs)
python -m ragevda.cli init -o config.yaml

# run a full audit from a config file
python -m ragevda.cli run -c config.yaml

# quick run without a config file (use YOUR real brand details)
python -m ragevda.cli quick \
    --brand "YourBrand" \
    --topics "your industry topic" "another topic" \
    --competitors CompetitorA CompetitorB \
    --depth 30

# interactive five-input wizard
python -m ragevda.cli interactive

# show run-history / drift trends for a brand
python -m ragevda.cli history --brand "YourBrand" --jobs-dir web_output/jobs
```

### Web UI

```bash
python -m ragevda.cli web --port 9000
# opens http://127.0.0.1:9000  (enterprise Material 3 UI, dark + light modes)
```

The web UI runs a 3-step flow — **Inputs → Deep Analysis → Outputs**:

- **Step 1 · Inputs.** Paste a brand **or any website URL** and hit
  ** Auto-Detect Deep Research**: the tool fetches the live site, scans
  discovery endpoints, runs budgeted live searches, and pre-fills **all 11
  configuration inputs** (topics, competitors, crawl depth, locality, intent +
  query templates, entity weighting/ontology, ground-truth paths, embedding
  model, SERP footprints, content feeds) with verified real-time data.
- **Step 2 · Deep Analysis.** ** Run Full Audit** executes all 10
  micro-engines with live progress, then opens the in-depth analysis: a global
  **Issues requiring attention** summary (CRITICAL / HIGH RISK / WATCH /
  STRENGTH), methodology + verification, and every engine's full computed
  detail with problem rows highlighted in red/amber/green.
- **Step 3 · Outputs.** ** Show Outputs** compiles the 12-section verified
  report (KPIs, leaderboard, full tables, downloads).

The web UI exposes **11 configuration inputs** on one form:

1. `target_brand` — your brand
2. `industry_topics` — 3–10 target concepts
3. `competitor_entities` — direct competitors
4. `crawl_depth` — results per query
5. `locality` — geo target
6. `search_intent` — informational / transactional / comparison / research / local / qa
7. `entity_weighting` — per-entity importance
8. `corpus_files` — owned ground-truth corpus
9. `embedding_model` — sentence-transformers checkpoint
10. `serp_footprints` — concrete AI-engine source URLs
11. `content_feeds` — competitor RSS / sitemap URLs

(plus optional `query_templates`). Each run writes a full report into
`web_output/jobs/<timestamp>-<hash>/` and appears in **History & Trends**.

Jobs queue persistently (SQLite) with a bounded worker pool
(`RAGEVDA_WORKERS`, default 2) — no more single-flight rejection. When
`RAGEVDA_API_KEY` (or `api_key`) is set, `/run` requires `X-API-Key` +
CSRF token and is per-IP rate-limited; every outbound fetch passes an SSRF
guard (no private/loopback hosts, validated redirect chain, optional
`fetch_allowlist`) and `robots.txt` is enforced.

### Enterprise API (FastAPI)

```bash
uvicorn ragevda.api:app --host 127.0.0.1 --port 9000
# GET  /health               → {"ok": true, "version": "2.2.0"}
# POST /jobs                 → {"job_id": ...}  (X-API-Key header)
# GET  /jobs/{id}            → status/progress/logs
# GET  /jobs/{id}/report     → full report.json
# OpenAPI docs at /docs; OTEL tracing when OTEL_EXPORTER_OTLP_ENDPOINT is set
```

### Deploy on Render (Docker) — LITE (free 512MB) vs FULL

**Live deployment:** https://rag-corpus-entity-vector-distance-auditor.onrender.com/

Two images, one codebase:

| | LITE (free tier / any gadget) | FULL (paid Starter 2GB+ / local) |
|---|---|---|
| Dockerfile | `Dockerfile.render` | `Dockerfile` |
| Deps | `requirements.render.txt` (no torch-CUDA, transformers, pandas, reportlab, faiss, fastapi) | `requirements.txt` / `pyproject.toml` |
| Deploy | `render.yaml` (`healthCheckPath: /health`) | `docker-compose.yml` |
| Embeddings | MiniLM-90MB | nomic-embed-text-v1.5 → BGE-M3 / Qwen3 |
| Hybrid + reranker | OFF | ON (`bge-reranker-v2-m3`) |
| Sentiment | lexicon fallback (labelled) | multilingual transformer + LLM-judge |
| Boot / audit RSS | ~180–250MB / ~380–450MB | ~400MB+ / ~1.8GB |
| Serving | gunicorn 1 worker × 2 threads, `--max-requests 50`, `--preload` | gunicorn 1 worker × 8 threads |

Required env on Render: `RAGEVDA_LITE=1`, `RAGEVDA_ALLOW_FALLBACK=1`,
`RAGEVDA_DISABLE_RERANKER=1`, `RAGEVDA_WORKERS=1` (all in `render.yaml`).
Optional: `HF_TOKEN` (silences HF rate limits), `RAGEVDA_API_KEY` (auth on
`/run`), `BRAVE_API_KEY` / `TAVILY_API_KEY` / `EXA_API_KEY` (live answer
sampling), `AI_CRAWLER_LOG` (AI-bot analytics), `GSC_CREDENTIALS` /
`GA4_PROPERTY` (attribution).

> **URL not loading? Checklist:** (1) Render must actually use the LITE
> image — either create the service as a **Blueprint** from `render.yaml`
> (New → Blueprint → select repo), or in an existing service set
> **Dockerfile Path** to `./Dockerfile.render` and redeploy; pushing the
> files alone changes nothing for manually-created services. (2) Read the
> **Events** tab: `Build failed` = see build logs (usually a pip/download
> error); `Out of memory` = still on the FULL `Dockerfile` (2GB+ image can
> never fit 512MB). (3) Free services **sleep when idle** — the first visit
> after inactivity takes ~60s to wake; `/health` must return
> `{"ok": true, ...}` once awake. The legacy `Dockerfile` pre-caches all models
at build time, runs as non-root, binds `0.0.0.0:$PORT`, and serves the Flask
UI via gunicorn (workers must stay 1: audits, scheduler and job cache live
in-process).

### Python API

```python
from ragevda.config import RunConfig
from ragevda.orchestrator import run

cfg = RunConfig(
    target_brand="YourBrand",
    industry_topics=["your main industry topic", "secondary topic"],
    competitor_entities=["CompetitorA", "CompetitorB"],
    crawl_depth=50,
    harvester="multi",               # multi | searxng | duckduckgo (fallback-only) | file
    answer_harvester="off",          # brave | tavily | exa | multi (needs API keys)
    require_real_models=True,          # never emit fake/degraded numbers
    output_dir="./ragevda_output",
)
report = run(cfg)
# report["proximity"], report["invisibility"], report["advanced"], ...
# report["advanced"]["eval"] → RAGAS-style gates; llms.txt/MCP written to output_dir
```

---

## Inputs — every field explained

### Core inputs

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `target_brand` | `str` |  | The exact brand / site name to audit. |
| `industry_topics` | `List[str]` |  (≥1) | High-value contextual topics / seed concepts (no limit). Each is embedded as a concept and compared. |
| `competitor_entities` | `List[str]` |  (≥1) | Direct competitor brand names (no limit). |
| `crawl_depth` | `int` (1–200) | | Results/pages scraped per query. Hard-capped at 200. |
| `locality` | `str \| None` | | Region / country code (e.g. `US`, `UK`, `Detroit`). `null` = global. |
| `harvester` | `str` | | `multi` (recommended: SearXNG + paid APIs + UGC) \| `duckduckgo` (fallback-only) \| `searxng` \| `answers` (paid keys) \| `file`. |
| `searxng_base_url` | `str \| None` | | Your self-hosted SearXNG URL (used when harvester is `searxng` or `prefer_searxng`). |
| `corpus_dir` / `corpus_files` | `str \| List[str]` | (file mode) | Local ground-truth corpus (owned PDFs, markdown, etc.). |

### Enterprise / advanced inputs

| Field | Type | Description |
|-------|------|-------------|
| `prefer_searxng` | `bool` | Make SearXNG primary when a URL is set, else DuckDuckGo. |
| `max_search_queries` | `int` (default 120) | Bounds live search calls. No limit on topics/competitors. |
| `max_pages` | `int` (default 200, 0=∞) | Max pages fetched. |
| `include_reddit` / `include_news` | `bool` | Add `topic reddit` / `topic news` queries. |
| `embedding_model` | `str` | `sentence-transformers` checkpoint. Auto-falls back to a real cached model if unavailable. |
| `spacy_model` | `str` | spaCy NER model. Auto-falls back to an installed real model. |
| `require_real_models` | `bool` (default **True**) | If True, aborts loudly instead of emitting degraded TF-IDF/regex numbers. **This is the anti-fabrication guarantee.** |
| `entity_aliases` | `Dict[str, List[str]]` | Alternate names per entity so a brand is not wrongly scored "omitted". |
| `entity_domains` | `Dict[str, List[str]]` | Owned domains per entity — a doc on that domain counts as a genuine mention. |
| `entity_weighting` | `Dict[str, float]` | Relative importance (e.g. brand at 1.5× a competitor). |
| `ontology_aliases` | `Dict[str, List[str]]` | Sub-brands / product modules / patents owned by an entity; merged into alias mention map. |
| `search_intent` | `str` | Retrieval surface: `informational` / `transactional` / `comparison` / `research` / `local` / `qa` (`commercial`/`navigational` legacy back-compat only). |
| `query_templates` | `Dict[str, str]` | Custom templates per intent; `{topic}` / `{brand}` substituted. |
| `content_feeds` | `List[str]` | Competitor/industry RSS + sitemap URLs for real-time ingestion. |
| `serp_footprints` | `List[str]` | Concrete source URLs per AI-engine surface; may be `engine|label|url`. |
| `chunk_tokens` / `chunk_overlap_tokens` | `int` | RAG window simulator (default 512 / 64). |
| `target_entity_density` | `float` (default 0.015) | Fraction of a window the brand should occupy to displace a competitor. |
| `top_k_retrieval` | `int` (default 5) | Retrieval depth simulated. |
| `engine_matrix` | `List[str]` | Engines scored: Google AI Overviews, SearchGPT, Gemini, Perplexity, Bing Copilot. |
| `drift_history_keep` | `int` (default 60) | Number of historical runs retained for drift. |
| `ollama_base_url` / `ollama_model` / `use_llm` | — | Local Ollama gap-analysis engine (e.g. `http://localhost:11434` / `llama3`). |
| `synthetic_query_count` | `int` (default 12) | Number of reverse-engineered retrieval queries. |
| `dedupe_near` / `near_dup_threshold` | `bool` / `float` | Remove exact + near-duplicate docs (default 0.95). |
| `random_seed` | `int` | Deterministic seeding. |

---

## Core features & functions — deep dive

### Feature A — Zero-cost headless web harvester

**Files:** `ragevda/harvester/{base,cleaner,duckduckgo,searxng,feeds,file_reader}.py`

The harvester pulls a **real, current corpus** without paying for a data vendor:

- **DuckDuckGo** (`duckduckgo.py`) — live SERP scraping of every expanded query,
  with automatic per-query fallback (if a query returns 0 results, it retries a
  progressive truncation) so no topic is silently dropped.
- **SearXNG** (`searxng.py`) — uses your self-hosted instance when configured.
  A pre-flight `ping()` probe tests connectivity **before** fanning out queries,
  so an unreachable SearXNG no longer causes a 120-query warning explosion or a
  silent 0-doc report. If SearXNG is unreachable it **auto-falls back to
  DuckDuckGo**.
- **Feeds & footprints** (`feeds.py`) — ingests RSS/sitemap `content_feeds`
  (real-time competitor articles) and explicit `serp_footprints` (concrete
  AI-engine citation URLs). A `_clean_url()` helper strips Markdown `[x](y)`
  wrappers and stray punctuation from pasted links.
- **File reader** (`file_reader.py`) — loads your own ground-truth corpus from
  disk (PDFs, markdown, text), capturing file mtime as the `Last-Modified`
  signal.

Each harvested document is wrapped in a `Document` with **provenance**: final
URL, HTTP status, SHA-1 content hash, fetch latency (`fetch_ms`), redirect chain,
and raw response **headers** (used later for freshness). Content is cleaned into
plain text by `trafilatura` (`cleaner.py`).

### Feature B — Local embeddings & semantic mapping

**Files:** `ragevda/nlp/embedder.py`, `ragevda/analysis/context.py`

- Loads a **real `sentence-transformers`** checkpoint fully locally.
- Chunks each document (default `sentence_chunk_chars=400`) and embeds every
  chunk into a normalized vector.
- Computes **cosine similarity** between topic/entity centroids and every
  document chunk.
- **Auto-calibrates relevance thresholds** per topic from the actual score
  distribution (no magic constants), so "high relevance" means something
  specific to *your* corpus.
- **Resilience:** if the requested model isn't cached, falls back to the best
  real cached checkpoint (`BAAI/bge-small` → `all-mpnet-base` → `MiniLM`)
  loaded in fully-offline mode (`HF_HUB_OFFLINE=1`).

### Feature C — Local NER & knowledge graph

**Files:** `ragevda/nlp/ner.py`, `ragevda/nlp/cooccurrence.py`

- spaCy NER extracts `ORG`, `PRODUCT`, `PERSON`, `GPE`, `WORK_OF_ART`, `EVENT`.
- Deterministic **mention detection** counts each brand/competitor/sub-brand via
  compiled, case-insensitive, word-boundary regex — with alias remapping so a
  synonym or sub-brand counts toward its parent and a brand is never wrongly
  scored "omitted".
- **Co-occurrence graph** (`networkx`) maps which entities appear together in
  the same document/chunk, powering poisoning and citation analyses.
- **Resilience:** if the requested spaCy model isn't installed, falls back to the
  best installed real model (`trf` → `lg` → `md` → `sm`).

### Feature D — Unlinked-authority & citation-gap finder

**Files:** `ragevda/analysis/{proximity,citation_gap,invisibility,recommendations}.py`

- **Proximity matrix** — every entity × every topic → semantic vector proximity
  (0–1) plus `docs_highly_relevant`, `support_mentions`, `confidence`, and the
  auto-calibrated `threshold_used`.
- **Citation gap** — for each entity, how many high-relevance docs *link* it vs
  *mention without linking* (`docs_linked` / `docs_unlinked` / `docs_omitted`).
- **RAG Invisibility Index** — % of high-relevance industry articles where the
  brand is absent while competitors are co-cited.
- **Vector Share of Voice** — the brand's presence inside the high-relevance
  retrieval corpus vs each competitor.
- **High-density off-page targets** — real URLs with high vector relevance that
  don't mention the brand yet (your pitch list).
- **Prioritized recommendations** — e.g. *"Priority 1: Pitch Publication X —
  they cited Competitor A N times in articles >0.80 similarity to your target
  topic."*

### Enterprise module 1 — Data-integrity verification / anti-fabrication

**File:** `ragevda/orchestrator.py`

A **verification score (0–100)** and `verified` flag are computed from real
signals: real models loaded, harvest success, support fraction, provenance
completeness, and live-source fraction. The config option
`require_real_models=True` (default) means the tool **aborts loudly instead of
silently emitting degraded TF-IDF/regex numbers** — this is what guarantees a
report is never accidentally fake. A low score honestly flags
"LOW CONFIDENCE"; it never hides it.

### Enterprise module 2 — Real-time source freshness & liveness

**File:** `ragevda/analysis/freshness.py`

Reads **real** `Last-Modified` / `Date` response headers and schema.org/meta
dates from the fetched HTML to compute per-source `age_days`, staleness
category (fresh / recent / stale / aging / unknown), liveness (HTTP 2xx), and
content-type. The aggregate appears as `live_fraction`, `fresh_pct`,
`median_age_days`, etc., and feeds into the verification score.

### Enterprise module 3 — Real ML sentiment (transformers)

**File:** `ragevda/analysis/sentiment.py`

Performs **sentence-granularity** sentiment scoring with the cached
`cardiffnlp/twitter-roberta-base-sentiment-latest` RoBERTa model, batched over
every sentence window around each entity mention. Outputs per-entity
positive/neutral/negative %, **net sentiment** in `[-1, 1]`, and **verbatim
negative-framed risk windows** (the exact retrieval text that could turn an AI
answer against the brand). The `method` and `model` are always reported honestly;
under `require_real_models=True` it hard-fails rather than use a lexicon.

### Enterprise module 4 — Data-driven per-engine share of voice

**File:** `ragevda/analysis/engine.py`

Removed fixed "affinity" priors. Per-engine Vector Share of Voice is now
**emergent** from real on-page retrieval features — authority, recency,
verbosity, title-directness, entity-richness — each document with a real
retrieval-propensity score. You get a topic × engine matrix where the engine
differences genuinely reflect the corpus.

### Enterprise module 5 — Real BPE token density & chunking

**File:** `ragevda/analysis/{chunking,density}.py`

- `count_tokens` / `token_windows` use a **real BPE tokenizer** from the cached
  embedding model — no magic 512-constant denominators.
- `mark_retrieved_windows` gates on the auto-calibrated relevance threshold.
- The token-density adjuster computes real per-window token ratios, real gaps,
  and a **displacement token plan** (how many on-window tokens the brand needs
  to displace a competitor's chunk from top-`k`).

### Enterprise module 6 — Statistical semantic-drift detection

**File:** `ragevda/analysis/drift.py`

Persists every run's metrics to `drift_timeseries.duckdb`. For each topic it
computes **linear-regression trend slopes** (`trend_proximity_per_run` etc.) over
the full history, **z-scores**, `data_points`, and **anomaly flags** (|z| ≥ 2).
You see whether your proximity is genuinely trending up/down, not just a
two-point delta.

### Enterprise module 7 — Vector poisoning / negative-SEO detection

**File:** `ragevda/analysis/poisoning.py`

Deterministically scores each source for thin content, link-farm density, toxic
off-topic co-citation that could drag your brand centroid toward junk topics.
Outputs a brand poisoning status (`clean` / `at-risk` / `compromised`), toxic
source lists, and per-entity exposure with `toxic_share_pct`.

### Enterprise module 8 — Synthetic query reverse-engineering

**File:** `ragevda/analysis/queries.py`

Generates the retrieval prompts each AI engine is likely issuing to pull each
entity's chunks (informational / transactional / comparison / research frames
applied to real topics + entities), each with a computed `retrieval_confidence`.
Brand-targeted queries become Q&A / FAQ content targets.

### Enterprise module 9 — RAG content brief & JSON-LD patch

**File:** `ragevda/reporting/brief.py`

Writes a `rag_content_brief.md` (per-topic: why the topic matters with real
proximity/leader numbers, retrieval gap, token action, entity placement) and a
`schema_jsonld_patch.json` (structured-data patch). Composed entirely from the
real computed metrics.

### Enterprise module 10 — Local-LLM (Ollama) gap analysis

**File:** `ragevda/nlp/llm.py`

When a local Ollama endpoint is reachable, produces free-text rationale for the
biggest gaps — **always injected with the real audited metrics and instructed
"Do not invent data."** If no LLM is available it degrades gracefully and notes
so, never faking content.

### Enterprise module 11 — Concurrency, dedup, and resilience

- Bounded `max_concurrency` HTTP fetch with per-request retry, timeout, and
  politeness.
- `dedupe_near` removes exact + near-duplicate harvested documents so counts are
  real, not inflated.
- Model, engine, and harvest failures are contained per-module so one bad input
  never kills the whole audit.

---

## Key metrics — the vocabulary of the report

* **Semantic Vector Proximity (0.0–1.0)** — how tightly bound an entity is to a
  topic (brand and each competitor).
* **RAG Invisibility Index (%)** — share of high-relevance industry articles
  where the brand is absent while competitors are co-cited.
* **Vector Share of Voice (%)** — brand's presence inside the high-relevance
  retrieval corpus vs competitors (per engine and overall).
* **Citation gap** (`linked / unlinked / omitted`) — how each entity is cited
  across high-relevance docs.
* **Net Sentiment (−1.0…+1.0)** — real RoBERTa sentiment toward the entity.
* **Token density (%) + tokens-to-displace** — the exact density the brand
  occupies in a retrieval window and the token budget to take a competitor's spot.
* **Freshness (live %, median age, staleness)** — real header-derived recency.
* **Poisoning risk (0–1) + status** — negative-SEO threat level.
* **Drift trend (/run) + anomaly flag** — statistical trajectory across runs.
* **Verification score (0–100) / verified** — authenticity of the run itself.
* **High-Density Off-Page Targets** — URLs/threads with high relevance that
  don't yet mention the brand.
* **Prioritized Recommendations** — concrete, real, actionable next steps.

---

## Outputs — every file explained

Every audit writes a self-contained folder (e.g. `ragevda_output/` or
`web_output/jobs/<timestamp>-<hash>/`):

| File | Kind | Contents |
|------|------|----------|
| `report.json` | JSON | The **complete machine-readable result** — proximity, citation gap, invisibility, SoV, recommendations, provenance, freshness, advanced (sentiment, sentiment matrix, engine matrix, visibility score, fan-out, citation funnel, token density, poisoning, drift, chunking, synthetic queries, crawler, GSC/GA4 attribution, LLM, eval gates + FactCheck fixes). |
| `dashboard.html` | HTML | A premium, self-contained, honest-data dashboard (proximity matrix, invisibility, SoV engine matrix, token-density adjuster, sentiment auditor, poisoning, drift trends, freshness, verification banner). |
| `rag_content_brief.md` | Markdown | Per-topic publishing guidance derived from real metrics, plus visibility / funnel / FactCheck / fan-out / word-association appendix. |
| `schema_jsonld_patch.json` | JSON | Structured-data patch for the RAG surface. |
| `action_plan.json` + `action_plan.md` | JSON/Markdown | Closed-loop execution: new-content stubs, refreshes, Reddit actions, outreach. |
| `wp_drafts/` | Markdown | WordPress-ready drafts per losing topic (front-matter + outline). |
| `llms.txt` / `llms-full.txt` | Text | Lean agent files for coding assistants (no ranking effect). |
| `agent.json` / `mcp.json` / `.well-known/mcp.json` / `.well-known/webmcp.json` | JSON | WebMCP-first agentic surface (Chrome 149 `navigator.modelContext`). |
| `proximity_scores.csv` | CSV | Topic × entity proximity, relevance counts, confidence, top sources. |
| `entity_citation_summary.csv` | CSV | Linked / unlinked / omitted citation counts per entity. |
| `off_page_targets.csv` | CSV | High-relevance URLs not yet mentioning the brand (pitch list). |
| `recommendations.csv` | CSV | Prioritized, real-data recommendations. |
| `invisibility_per_topic.csv` | CSV | Invisibility % per topic. |
| `sources.csv` | CSV | Per-doc provenance + freshness (URL, title, source type, domain, status, hash, latency, age, staleness, live, content-type). |
| `verification.csv` | CSV | Verification score, models_real, exact embedding/NER/sentiment models, fresh %, live %. |
| `sentiment_audit.csv` | CSV | Per-entity sentiment percentages and net score. |
| `sentiment_risk_windows.csv` | CSV | Verbatim negative-framed brand windows. |
| `share_of_voice_heatmap.csv` | CSV | Vector SoV per topic per engine. |
| `token_density_adjuster.csv` | CSV | Real BPE token counts + displacement plan. |
| `poisoning_sources.csv` / `poisoning_exposure.csv` | CSV | Toxic co-citing sources and entity exposure. |
| `semantic_drift.csv` | CSV | Proximity/invisibility/SoV deltas, trend slopes, data points, anomaly. |
| `source_freshness.csv` | CSV | Per-source liveness, age, staleness, latency, content-type. |
| `synthetic_retrieval_queries.csv` | CSV | Reverse-engineered retrieval prompts + confidence. |
| `corpus.duckdb` | DB | The full local vector/corpus store (SQL-queryable, $0). |
| `drift_timeseries.duckdb` | DB | Persistent cross-run time-series for drift. |
| `looker_connector.json` + `looker_rows.csv` | JSON/CSV | Looker Studio connector bundle (stdlib csv, LITE-safe). |
| `report.pdf` | PDF | (web UI) a **~17-page enterprise report**: cover + KPI cards, captioned charts, per-section issue callouts, color-coded cells, all 10 engines and the full outputs ledger. Served from `web_output/jobs/<…>/`; stale copies auto-regenerate on download. |

---

## Schema — the report.json contract

```jsonc
{
  "meta": {
    "tool": "RAG-EVDA", "version": "2.1.1", "generated_at": "...Z",
    "config": { /* every RunConfig field */ },
    "embedding_kind": "sentence-transformers",
    "embedding_model": "BAAI/bge-small-en-v1.5",
    "ner_kind": "spacy",
    "ner_model": "en_core_web_sm",
    "context_stats": { "doc_count": 125, "graph": { ... } },
    "harvest_stats": { ... },
    "data_integrity": {
      "models_real": true,
      "embedding_model": "...", "ner_model": "...", "sentiment_model": "...",
      "harvest_ok": true, "harvested_docs": 125, "dedup_removed": 185,
      "live_fraction": 1.0, "freshness_summary": { ... },
      "verification_score": 91.0, "verified": true
    },
    "verification_score": 91.0, "verified": true
  },
  "proximity": { "rows": [ { "topic": "...", "entity": "...",
                             "proximity": 0.60, "label": "Moderate",
                             "docs_highly_relevant": 6, "support_mentions": 159,
                             "confidence": "high", "threshold_used": 0.7051,
                             "top_sources": [ { "url":"...", "title":"...",
                                                "topic_relevance": 0.73 } ] } ] },
  "citation_gap": { "entity_summary": [ ... ] },
  "invisibility": { "per_topic": [ ... ], "overall": { ... } },
  "recommendations": [ ... ],
  "provenance": [ { "doc_id":"...", "url":"...", "title":"...", "source_type":"web",
                    "age_days":1.2, "staleness":"fresh", "live":true, ... } ],
  "freshness": { "summary": { "live_pct":100.0, "fresh_pct":100.0,
                              "median_age_days":2.1, ... }, "per_source": [ ... ] },
  "advanced": {
    "sentiment": { "method":"transformer-roberta-sentiment-latest",
                   "model":"cardiffnlp/twitter-roberta-base-sentiment-latest",
                   "per_entity":[ ... ], "risk_windows":[ ... ] },
    "engine_matrix": { "method":"...", "cells":[ ... ] },
    "token_density": { "method":"real-token ...", "per_topic":[ ... ],
                       "brand_displacement_readiness": 42 },
    "poisoning": { "brand_poisoning_status":"clean", "sources":[ ... ],
                   "entity_exposure":[ ... ] },
    "drift": { "per_topic":[ { "topic":"...", "data_points":1,
                              "trend_proximity_per_run":0.0, "anomaly":false } ],
               "alerts":[ ... ] },
    "chunking": { "window_count":..., "retrieved_count":..., "tokens_processed":...,
                  "chunk_tokens":512, "chunk_overlap_tokens":64 },
    "synthetic_queries": { "per_entity": { ... } },
    "llm": { "available": false, "note": "..." }
  }
}
```

---

## Real worked example — a live The Guardian audit

Below is **genuine output** from a real RAG-EVDA run (`web_output/jobs/20260830-094637-26b22b`),
harvested from the live open web. Numbers are real: real documents, real
embeddings, real NER counts, real source URLs.

**Run:** brand *The Guardian* · 125 documents after dedup · real
`BAAI/bge-small-en-v1.5` embeddings · real `en_core_web_sm` NER · real RoBERTa
sentiment · most-relevant topic threshold **0.7051**.

### Vector proximity on "Digital Journalism & Independent Media"

| Entity | Proximity | Label | Highly-relevant docs | Support mentions | Confidence |
|--------|-----------|-------|----------------------|------------------|------------|
| The New York Times | 0.6487 | Moderate | 7 | 34 | high |
| **The Guardian** | **0.6012** | Moderate | 6 | 159 | high |
| BBC News | 0.6034 | Moderate | 3 | 12 | high |
| The Washington Post | 0.5902 | Moderate | 4 | 22 | high |
| The Financial Times | 0.5902 | Moderate | 3 | 19 | high |

*The Guardian* is out-proximitized by The New York Times (0.6012 vs 0.6487) on
this topic despite the highest raw support-mention count (159) — exactly the
"high volume, sub-optimal vector placement" signal RAG-EVDA is built to surface.

### Real source evidence (live URLs the auditor actually scored)

- `https://theaudiencers.com/the-guardian-reader-revenue-growth-proposition-development/` — topic_relevance **0.7398**
- `https://shorthand.com/the-craft/investigative-journalism-examples/` — **0.729**
- `https://www.theguardian.com/help/insideguardian/2026/mar/04/how-the-guardian-is-using-genai` — **0.7249**
- (New York Times top source) `https://eliteedgeenterprise.com/news-business-models-2026-shift-to-reader-revenue/` — **0.7705**
- (BBC top source) `https://reutersinstitute.politics.ox.ac.uk/digital-news-report/2026/dnr-executive-summary` — **0.7455**

### The 22 output files that run produced

`corpus.duckdb` (11.5 MB), `dashboard.html` (172 KB), `drift_timeseries.duckdb`,
`entity_citation_summary.csv`, `invisibility_per_topic.csv`, `off_page_targets.csv`,
`poisoning_exposure.csv`, `poisoning_sources.csv`, `proximity_scores.csv`,
`rag_content_brief.md`, `recommendations.csv`, `report.json` (463 KB),
`schema_jsonld_patch.json`, `semantic_drift.csv`, `sentiment_audit.csv`,
`sentiment_risk_windows.csv`, `share_of_voice_heatmap.csv`,
`source_freshness.csv`, `sources.csv`, `synthetic_retrieval_queries.csv`,
`token_density_adjuster.csv`, `verification.csv`.

>  **This is real data, not a demo.** The URLs are live pages, the hashes and
> latencies came from real HTTP responses, the entities were counted by real
> spaCy NER, and the sentiment by a real transformer. RAG-EVDA's verification
> layer reports the run's confidence honestly (here `verified: false` / 72 due
> to partial support-fraction — the tool always shows its true confidence rather
> than dressing it up).

---

## Live screenshots — real output from the The Guardian audit

> These are **actual rendered screenshots** of the self-contained `dashboard.html`
> produced by the real The Guardian run above (job
> `web_output/jobs/20260830-094637-26b22b`, captured 2026-08-30). They are full-color
> captures of the live report — real tables, real scores, real source URLs — **not**
> mockups or dummy data. Every file under [`assets/`](assets/) is unique
> (SHA-256 verified, no duplicates) and maps 1:1 to that job's `report.json`.

### Full-page dashboard (scroll view, 760px WebP)

![RAG-EVDA full dashboard — The Guardian audit](assets/dashboard_full.webp)

### Brand health issues

![Brand health issues — real audit](assets/brand_health.png)

### Semantic vector proximity matrix (topic × entity)

![Semantic vector proximity matrix — real audit](assets/proximity_matrix.png)

### Per-topic RAG invisibility & share of voice

![Per-topic RAG invisibility & share of voice — real audit](assets/invisibility_sov.png)

### Entity link vs. mention audit

![Entity link vs. mention audit — real audit](assets/citation_gap.png)

### High-density off-page target list (real URLs to pitch)

![High-density off-page target list — real audit](assets/offpage_targets.png)

### Prioritized recommendations (real, data-driven)

![Prioritized recommendations — real audit](assets/recommendations.png)

### Real-time source freshness & liveness (also feeds the per-engine SoV view)

![Real-time source freshness & liveness — real audit](assets/freshness.png)

### Automated token-density adjuster (real BPE counts)

![Automated token-density adjuster — real audit](assets/token_density.png)

### RAG chunk sentiment auditor + verbatim negative-framed brand windows (real RoBERTa)

![RAG chunk sentiment auditor and risk windows — real audit](assets/sentiment.png)

### Vector poisoning / negative-SEO detection

![Vector poisoning / negative-SEO detection — real audit](assets/poisoning.png)

### Semantic drift tracking (time-series deltas & trends)

![Semantic drift tracking — real audit](assets/drift.png)

### Synthetic query generator (reverse-engineered RAG prompts)

![Synthetic query generator — real audit](assets/synthetic_queries.png)

### RAG chunking & contextual-window simulator

![RAG chunking & contextual-window simulator — real audit](assets/chunking.png)

### Data provenance — harvested real sources

![Data provenance — harvested sources — real audit](assets/provenance.png)

All screenshots live under [`assets/`](assets/). Every run the web UI / CLI
completes produces the same class of visual report via its self-contained
`dashboard.html`.

---

## DuckDB — the local vector database

Every audit writes a `corpus.duckdb` — a single-file, SQL-queryable vector +
document store:

- `Document` records with text, URL, hash, headers, freshness
- chunk embeddings per document
- entity centroids

You can query it directly:

```sql
-- DuckDB CLI / any DuckDB client
SELECT url, title, http_status, age_days, staleness FROM sources ORDER BY age_days;
SELECT entity, docs_linked, docs_unlinked FROM entity_summary;
```

`drift_timeseries.duckdb` persists cross-run metrics so `ragevda.cli history`
and the drift module can compute trends. Storage is entirely local — nothing
leaves your machine.

---

## Recurring / scheduled audits & drift history

`ragevda/scheduler.py` + `ragevda/tracking.py`:

- Schedule recurring full audits; each fire runs a normal live audit and writes
  a normal report into `web_output/jobs/…` (so History & Trends and the drift
  time-series accumulate real data points).
- Run-history/trends view (`python -m ragevda.cli history --brand …`) shows
  your proximity / invisibility / SoV trajectory across runs.

---

## Configuration reference — full YAML

```yaml
# ================= RAG-EVDA inputs =================
# 1) TARGET BRAND (use your real brand/company name)
target_brand: "YourBrand"

# 2) TARGET INDUSTRY TOPICS / CONCEPTS (no limit, use real topics)
industry_topics:
  - "your main industry topic"
  - "secondary topic"

# 3) COMPETITOR ENTITIES (no limit, use real competitor names)
competitor_entities:
  - "CompetitorA"
  - "CompetitorB"

# 4) CRAWL DEPTH (1-200)
crawl_depth: 50

# 5) LOCALITY / GEO TARGET (null = global)
locality: null

# ----- engine settings (usually leave alone) -----
harvester: "multi"                 # multi | searxng | file | duckduckgo (fallback-only) | answers
answer_harvester: "multi"          # off | brave | tavily | exa | multi (keys via BRAVE/TAVILY/EXA env)
answer_repeats: 5                  # 5-10x per prompt (probabilistic noise sampling)
searxng_base_url: null
corpus_dir: null
include_reddit: true
include_news: true
embedding_model: "nomic-ai/nomic-embed-text-v1.5"   # FULL default; LITE uses MiniLM-90MB
spacy_model: "en_core_web_sm"
output_dir: "./ragevda_output"
require_real_models: true          # never emit fake/degraded numbers

# ----- enterprise / advanced -----
search_intent: "informational"     # informational|transactional|comparison|research|local|qa
chunk_tokens: 512
chunk_overlap_tokens: 64
target_entity_density: 0.015
top_k_retrieval: 5
engine_matrix:
  - "Google AI Overviews"
  - "SearchGPT"
  - "Gemini"
  - "Perplexity"
  - "Bing Copilot"
content_feeds: []                  # competitor RSS / sitemap URLs
serp_footprints: []                # engine|label|url
entity_aliases: {}                 # {entity: [alias, ...]}
entity_domains: {}                 # {entity: [domain, ...]}
entity_weighting: {}               # {entity: weight}
ollama_base_url: null              # e.g. http://localhost:11434
ollama_model: "llama3"
```

---

## Extending toward the polyglot architecture

The product brief describes a Go/Rust scraping layer + React dashboard. This
repository is a complete, runnable **Python core** (the AI/vector engine). The
storage (`DuckDB`) and reporting (`CSV/JSON/HTML`) layers are already decoupled,
so a Go/Rust harvester can write into `corpus.duckdb` and a React frontend can
read `report.json` without touching the analysis code. `dashboard.html` is
self-contained, so it can be embedded or served by any static host.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `SearXNG probe UNREACHABLE … fell back to DuckDuckGo` | Your SearXNG URL is unreachable (`localhost:8080` not listening, or a `.internal` hostname that can't resolve) | Point `searxng_base_url` at a reachable instance, or rely on the automatic DuckDuckGo fallback. This is working-as-designed, not an error. |
| `Can't find model 'en_core_web_trf'` or `bge-large … 401` | You requested a model that isn't installed/cached | The tool now **auto-falls back** to the best real locally-available model. To use the exact model, `python -m spacy download en_core_web_trf` / `huggingface-cli download <model>`. |
| `cannot read /docs/corpora/… : No such file` | Your `corpus_files` paths don't exist on this machine | Create those files, or remove them from config. The tool logs this and continues (0 docs from that source). |
| Many `HTTP 403/401/402` warnings during fetch | Paywalled / bot-blocked sites (Wikipedia, FT, Telegraph, WaPo) | Expected. The tool skips them and only keeps genuinely fetchable pages. |
| `verification_score` low / `verified: false` | Low support fraction or partial provenance of the harvested corpus | Not a tool failure — it means the run's confidence is honestly low. Improve corpus quality/coverage. |
| Browser still shows the old UI after updating | The Flask server (`python -m ragevda.cli web`) loads code once at startup — it does not hot-reload | Restart the server process, then hard-refresh (`Ctrl+Shift+R`). The running PID is shown by the OS process list; kill it and re-run the same command. |
| Downloaded PDF looks like the old layout | A `report.pdf` cached from a previous version was served | Fixed in v1.3.0: the server auto-rebuilds any PDF older than the generator on next download. On older checkouts, delete the job's `report.pdf` and re-download. |
| Audit "stuck" at one % for many minutes | Slow hosts / rate-limited search + a silent CPU stretch (mention scan, centroid encoding, transformer sentiment over hundreds of windows) | v2.1.1+: the run always advances — named phase markers move the bar 6→98%, a 45s `still working` heartbeat proves liveness in the console, harvest honors `RAGEVDA_HARVEST_TIMEOUT` (default 480s) and UGC honors `RAGEVDA_UGC_TIMEOUT` (default 90s) instead of stalling forever. If the log shows `harvest deadline` / `UGC budget exhausted`, the audit correctly continued with partial results — narrow scope for a faster run (below). |
| Audit takes very long overall | 200 pages × retries + CPU embeddings + transformer sentiment | Reduce scope (`max_pages: 40–80`, `crawl_depth: 10–20`, `max_search_queries: 30–50` — `0` = unlimited, big box only), use `RAGEVDA_LITE=1` (lexicon sentiment skips the ~600MB one-time transformer download), tune fetch via `RAGEVDA_FETCH_TIMEOUT` (default 20s) / `RAGEVDA_MAX_CONCURRENCY` (default 8) / `RAGEVDA_HARVEST_TIMEOUT` (default 480s) / `RAGEVDA_UGC_TIMEOUT` (default 90s), or add Brave/Tavily/Exa keys so fewer dead-end fetches are needed. A 200-page FULL audit takes ~15–45 min on laptop CPU; a triage config above takes ~3–5 min. |

---

## Responsible use

* **Estimates, not guarantees.** All scores are model-derived. Treat them as
  decision support, then verify outreach manually.
* **Be polite.** The harvester uses a small default concurrency (8) and respects
  a per-query depth cap (hard-capped at 200). Honor each site's `robots.txt` and
  Terms of Service, and throttle if needed.
* **DuckDuckGo / SearXNG availability.** Zero-cost search can rate-limit or
  block. For production volume run your own SearXNG (`harvester: searxng`,
  `searxng_base_url: …`) or use `file` mode.
* **No data leaves your machine.** Embeddings, NER, sentiment, storage, and
  reporting all run locally.
* **The tool is honest about itself.** `require_real_models=True` guarantees no
  synthetic numbers are silently emitted, and the verification layer always
  reports real confidence — even when that confidence is low.

---

## About

**RAG-EVDA — RAG Corpus Entity & Vector Distance Auditor (v2.1.1)** is a zero-cost,
fully-local intelligence engine for AI-search visibility. It decodes how modern
generative search engines (Gemini, SearchGPT, Google AI Overviews, Perplexity,
Bing Copilot) semantically perceive your brand relative to competitors inside a
retrieval-augmented generation corpus — turning "AI SEO guessing" into exact,
actionable vector mathematics. No proprietary API keys. No data leaves your
machine. Every number is real, verifiable, and enterprise-grade — the v1.2.0
hardening release removed every synthetic fallback and demo fixture so reports
are built exclusively on live fetches and local ML inference, and v1.3.0
wrapped it in an enterprise-grade experience (2026 UI, issue highlighting,
full PDF, outputs hub).

---

## Changelog

### v2.2.0 — Enterprise GEO-depth release
- **Fixed:** paid fan-out now covers ALL queries (RRF-merged ThreadPool batch,
  was `queries[0]` only) with concurrent fetching; scheduler tick race
  (snapshot-under-lock, callback outside lock); defaults now GEO-real
  (`harvester/answer_harvester: multi`, 6 standard intents, TikTok opt-in,
  `generate_llms_txt: false`).
- **Added:** 10 P0 engines in `advanced` (citation stealer, fan-out coverage,
  E-E-A-T gate, entity-gain, reddit topics, media checks, multilingual,
  white-label/MCP, prompt volumes + daily snapshots + drift alerts) plus
  `docs/` (`EMBEDDINGS.md`, `SERVING.md`, `SCOPE_2026.md`) and CI
  `version-check`. Suite: 59 passed, 9 skipped.
- Full details in [`CHANGELOG.md`](CHANGELOG.md).

### v2.1.1 — Audit-always-completes release
- **Fixed:** audit no longer stalls looking "stopped at X%" — named phase
  markers across all 10 engines, monotonic 6→98% progress mapping, 45s
  heartbeat watchdog, `RAGEVDA_HARVEST_TIMEOUT` (480s) + `RAGEVDA_UGC_TIMEOUT`
  (90s) time-boxes, UGC capped to 5 seed queries/source, single DDG fallback
  variant.
- Full details in [`CHANGELOG.md`](CHANGELOG.md).

### v1.3.0 — Enterprise experience release
- **Added:** enterprise 2026 web UI (hero, bento inputs, 3-step flow, Show
  Outputs, toasts, live progress); deep-research Auto-Detect for all 11
  inputs; issue-highlighting framework (cards, banners, flagged rows) across
  all 10 engines; ~17-page enterprise PDF with charts + callouts; 12-section
  outputs hub; stale-PDF auto-heal on download.
- **Fixed:** Material 3 light-mode token mismatch; dark-only hardcoded colors.
- Full details in [`CHANGELOG.md`](CHANGELOG.md).

### v1.2.0 — Real-data hardening release
- **Removed all synthetic/demo paths:** TF-IDF/lexicon/char-4 fallbacks now hard-fail
  under `require_real_models=True` (default) instead of silently degrading; fabricated
  deep-analysis provenance rows deleted (real `report.json` provenance only);
  `SmokeBrand`/`Acme` demo jobs and empty failed runs purged.
- **Correctness fixes:** case-insensitive co-occurrence graph (bind strength was always 0);
  real per-mention BPE token spans (was chars/4 estimate); PDF/narrative percent
  scaling (was 1810%/10000%); 3-state `VERIFIED/PARTIAL/UNVERIFIED` badge everywhere;
  verbatim sentiment `snippet` rendering; word-boundary anchor matching.
- **Coverage:** PDF ground-truth ingestion (`pypdf`), `commercial`/`navigational` intents,
  real-data JSON-LD (competitor-aware), file-corpus honesty (`live=False`, hash+mtime
  provenance), offline-first sentiment/tokenizer loading, scheduler↔web-run parity,
  pinned `flask`/`transformers`/`huggingface_hub`/`reportlab`/`pypdf` dependencies.

---

## Tags

`rag` · `ai-search` · `seo` · `vector-search` · `embeddings` · `ner` ·
`sentence-transformers` · `rag-seo` · `retrieval-augmented-generation` ·
`share-of-voice` · `semantic-search` · `duckdb` · `spacy` · `local-llm` ·
`drift-detection` · `sentiment-analysis` · `competitive-intelligence` ·
`brand-audit` · `vector-database` · `ai-visibility` · `perplexity` ·
`gemini` · `searchgpt` · `google-ai-overviews` · `bing-copilot` ·
`tokenization` · `knowledge-graph` · `negative-seo` · `content-brief` ·
`json-ld` · `offline-first`

---

## Roadmap

Near-term: hosted sample dashboard (`gh-pages`), release artifacts with sample
`report.json`, auto_probe/deep_analysis module splits, real `robots.txt`
enforcement hardening, 60% test coverage, EVAL v2 (hand-labeled citation-gap
precision/recall + RAGAS comparison). Full list in [`ROADMAP.md`](ROADMAP.md) —
contributions welcome per [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Author

**Dipak Jadhav** ([@dipakjad1993](https://github.com/dipakjad1993)) — Applied AI
engineer building cost-aware, fully-local LLM systems. Open to Applied LLM /
MLOps / MarTech-SEO roles. Star  the repo if auditable AI visibility matters
to you.

---

## License

**MIT** — use it, improve it, and stop buying low-tier links in a 2016 bubble.
