# RAG-EVDA — RAG Corpus Entity & Vector Distance Auditor

![CI](https://github.com/dipakjad1993/RAG-Corpus-Entity-Vector-Distance-Auditor/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![Local-only](https://img.shields.io/badge/LLM-100%25%20local-orange)
![Version](https://img.shields.io/badge/version-2.3.0-black)
[![Live demo](https://img.shields.io/badge/demo-live%20on%20Render-brightgreen)](https://rag-corpus-entity-vector-distance-auditor.onrender.com/)

> **Try it live:** https://rag-corpus-entity-vector-distance-auditor.onrender.com/ — full UI with Auto-Detect, Deep Analysis and Outputs hub. Render free tier sleeps, so the first visit after idle takes ~60s to wake.
>
> **No-wait sample:** `docs/sample_dashboard/` (static redacted report, always awake) — see `docs/SAMPLE_DASHBOARD.md`. Tour storyboard: `docs/TOUR.md`.

> **A zero-cost, fully-local intelligence engine that decodes how modern AI search engines — ChatGPT, Gemini, Claude, Perplexity, Copilot, Grok, Meta AI, DeepSeek, Google AI Overviews, Google AI Mode — semantically perceive your brand versus competitors inside a retrieval-augmented generation (RAG) corpus. Then it tells you exactly what to publish to change that perception.**
>
> No OpenAI / Ahrefs / Semrush / BrightEdge keys. No data leaves your machine. Every number is backed by a real URL, content hash and fetch latency. Current version: **2.3.0**.

| | | |
|---|---|---|
| **125 docs** audited in the reference Guardian run | **$0** API cost, forever | **Full output bundle** per run (JSON + HTML + DuckDBs + brief + action plan + Looker) |

## Contents

* [Why it exists](#why-it-exists)
* [Proof, not promises](#proof-not-promises)
* [Why not a black-box SaaS?](#why-not-a-black-box-saas)
* [What's new in 2.3.0](#whats-new-in-230)
* [Installation](#installation)
* [Quick start (CLI)](#quick-start-cli)
* [Web UI](#web-ui)
* [Enterprise API](#enterprise-api)
* [Python API](#python-api)
* [Inputs](#inputs)
* [Features](#features)
* [Key metrics](#key-metrics)
* [Outputs](#outputs)
* [Deploy (LITE vs FULL)](#deploy-lite-vs-full)
* [Docs](#docs)
* [Troubleshooting](#troubleshooting)
* [Responsible use](#responsible-use)
* [Roadmap / Contributing / Author / License](#roadmap--contributing--author--license)

## Why it exists

AI search doesn't "look up" your site like a 2016 crawler. It embeds the query as a vector, retrieves the top-k corpus chunks closest to it (RAG), and composes an answer from them. **If your brand entity sits far from your industry topics in that vector space, you never get retrieved — no matter how many backlinks you have.**

The 2026 numbers make this urgent: AI Overviews appear on ~48% of US queries, 62–83% of their citations come from pages *outside* the organic top-10, Reddit alone drives ~22% of AI citations, and unlinked brand mentions correlate with AI visibility at r≈0.7 versus r≈0.2 for raw backlink count.

RAG-EVDA turns AI-SEO guessing into auditable math: it harvests the real pages defining your niche, embeds them with local models, and computes your brand's exact semantic distance from each topic and competitor — plus the concrete pitch list and publishing plan to close the gap.

## Proof, not promises

Genuine output from a live run (`web_output/jobs/20260830-094637-26b22b`): brand *The Guardian*, 125 documents after dedup, real local embeddings + NER + transformer sentiment.

| Entity | Proximity | Label | Highly-relevant docs | Mentions |
|---|---|---|---|---|
| The New York Times | **0.6487** | Moderate | 7 | 34 |
| The Guardian | 0.6012 | Moderate | 6 | **159** |
| BBC News | 0.6034 | Moderate | 3 | 12 |
| The Washington Post | 0.5902 | Moderate | 4 | 22 |

The Guardian is out-proximitized by NYT *despite 5x the mention volume* — the "high volume, sub-optimal vector placement" signal this tool is built to surface. Top evidence URLs, hashes and latencies ship with every run (`sources.csv` / `report.json`).

## Why not a black-box SaaS?

| | RAG-EVDA 2.3.0 | Profound / Peec / Otterly-style SaaS | Semrush / Ahrefs |
|---|---|---|---|
| Cost | $0 local | ~$29–$25k/mo | ~$99–$499/mo |
| Data leaves machine | Never | Yes (black-box score) | Yes |
| Metric | Auditable vector math (proximity / invisibility / token-displacement) | Proprietary score | Ranks / backlinks |
| Provenance | Full DuckDB + hashes + latencies, reproducible offline | Not inspectable | Vendor trust |
| Volatility | Mean ± stdev + citation decay (`docs/VOLATILITY.md`) | Single-sample dashboard | n/a |
| Fix loop | `action_plan` + `wp_drafts/` + FactCheck fixes | Export CSV, good luck | Separate product |

## What's new in 2.3.0

* **TL;DR Executive Verdict card** — Visibility 0–100, Position rank, Mentions vs linked-citations split and Δ vs competitor median on top of every dashboard (`docs/EXEC_VERDICT.md`). Built for the LinkedIn screenshot.
* **Answer volatility + citation decay** — per-prompt mean ± stdev over `answer_repeats` (STABLE / WATCH / VOLATILE ladder) plus week-over-week SoV decay from drift history. Single-sample runs are labelled UNKNOWN, never smoothed (`docs/VOLATILITY.md`).
* **Full P0-engine dashboard** — visibility, query fan-out, E-E-A-T gate, entity-density + Information Gain, subreddit map, media checks, multilingual report, AI-crawler analytics, GSC/GA4 attribution cards. All fail-open, all from real report evidence.
* **Real robots.txt enforcement** (`ragevda/harvester/robots.py`, fail-open, cached) and an **EVAL v2** hand-labelling harness for citation-gap precision/recall (`docs/EVAL_V2.md`).
* **Packaging reset** — this README went 1,324 → ~300 lines (full reference preserved at `docs/GUIDE_FULL.md`), FastAPI-first serving docs, gh-pages sample + PyPI/GHCR publish workflows.
* Full history: `CHANGELOG.md`.

## Installation

Requirements: Python 3.10+, ~1.8 GB free for FULL models (~450 MB for LITE), and the spaCy English model.

```bash
# 1. clone, then create a venv
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

# 2. install (uv preferred; pip shim also works)
uv sync
# ...or: pip install -r requirements.txt

# 3. NER model
python -m spacy download en_core_web_sm

# 4. (recommended) pre-cache embedding + sentiment models so audits run offline
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5')"

# 5. verify
python -m ragevda.cli --version   # → ragevda 2.3.0
python -m pytest tests/ -q        # → 70 passed, 9 skipped
```

Resilience guarantee: if a requested model isn't cached, RAG-EVDA falls back to the best real locally-available model instead of crashing — and with `require_real_models: true` (default) it aborts loudly rather than emitting degraded numbers. The TF-IDF fallback is explicit opt-in only (`RAGEVDA_ALLOW_FALLBACK=1`).

## Quick start (CLI)

```bash
# offline demo in ~30s, no network: 10 sample docs → dashboard.html
python -m ragevda.cli run -c examples/offline_demo/config.yaml

# generate a starter config (interactive prompts for real inputs)
python -m ragevda.cli init -o config.yaml

# full audit from a config file
python -m ragevda.cli run -c config.yaml

# quick run without a config file (use YOUR real brand details)
python -m ragevda.cli quick \
    --brand "YourBrand" \
    --topics "your industry topic" "another topic" \
    --competitors CompetitorA CompetitorB \
    --depth 30

# five-input interactive wizard
python -m ragevda.cli interactive

# run-history / drift trends for a brand
python -m ragevda.cli history --brand "YourBrand" --jobs-dir web_output/jobs
```

Every run is time-boxed and observable: named phase markers move progress 6→98%, a 45s heartbeat proves liveness on slow networks, and harvest/UGC honor `RAGEVDA_HARVEST_TIMEOUT` (480s) / `RAGEVDA_UGC_TIMEOUT` (90s) instead of stalling.

## Web UI

```bash
python -m ragevda.cli web --port 9000
# → http://127.0.0.1:9000 (local operator UI; dark + light modes)
```

Three steps — **Inputs → Deep Analysis → Outputs**:

1. **Inputs.** Paste a brand or URL and hit Auto-Detect: live reconnaissance (homepage, robots/sitemap, JSON-LD, topic/competitor searches, Wikipedia check) pre-fills all 11 fields — brand, topics, competitors, crawl depth, locality, intent + query templates, entity weighting/ontology, ground-truth files, embedding model, SERP footprints, content feeds.
2. **Deep Analysis.** Run Full Audit executes every engine with live progress, then shows a global CRITICAL / HIGH RISK / WATCH / STRENGTH summary plus per-engine banners and red/amber/green flagged rows.
3. **Outputs.** Show Outputs compiles the 12-section verified report with the TL;DR verdict card and all downloads into `web_output/jobs/<timestamp>-<hash>/`.

Jobs queue persistently (SQLite, `RAGEVDA_WORKERS` pool). With `RAGEVDA_API_KEY` set, `/run` requires X-API-Key + CSRF token with per-IP rate limiting; every fetch passes an SSRF guard and robots.txt is enforced.

## Enterprise API

FastAPI is the enterprise path (Flask `webapp.py` is the local operator UI only — never serve production API traffic from it, and never run both on the same port).

```bash
uvicorn ragevda.api:app --host 127.0.0.1 --port 9000
# GET  /health               → {"ok": true, "version": "2.3.0"} (model-free)
# POST /jobs                 → {"job_id": ...}  (X-API-Key header)
# GET  /jobs/{id}            → status / progress / logs
# GET  /jobs/{id}/report     → full report.json
# OpenAPI at /docs; OTEL tracing when OTEL_EXPORTER_OTLP_ENDPOINT is set
```

## Python API

```python
from ragevda.config import RunConfig
from ragevda.orchestrator import run

cfg = RunConfig(
    target_brand="YourBrand",
    industry_topics=["your main industry topic", "secondary topic"],
    competitor_entities=["CompetitorA", "CompetitorB"],
    crawl_depth=50,
    harvester="multi",            # multi | searxng | duckduckgo (fallback) | file | answers
    answer_harvester="multi",     # off | brave | tavily | exa | multi (keys via env)
    answer_repeats=5,             # 5–10 for real volatility stats
    require_real_models=True,     # never emit fake/degraded numbers
    output_dir="./ragevda_output",
)
report = run(cfg)
# report["proximity"], report["invisibility"], report["advanced"]["visibility"],
# report["advanced"]["volatility"], report["advanced"]["drift"], ...
```

Presets: `RunConfig.full_profile(...)` (paid/local workstation) and `RunConfig.lite_profile(...)` (free-tier/phone), plus `apply_env_overrides()` for `RAGEVDA_LITE` / `RAGEVDA_ALLOW_FALLBACK` / fetch tuning.

## Inputs

Core inputs:

| Field | Type | Notes |
|---|---|---|
| `target_brand` | str | Your exact brand / site name (placeholders blocked) |
| `industry_topics` | List[str] | 1–20 real topics; each embedded as a concept |
| `competitor_entities` | List[str] | 1–15 real competitors |
| `crawl_depth` | int 1–200 | Pages scraped per query |
| `locality` | str \| None | e.g. `US`, `UK`; null = global |
| `harvester` | str | `multi` (SearXNG + paid APIs + UGC, recommended) · `duckduckgo` fallback-only · `searxng` · `answers` · `file` |
| `answer_harvester` | str | `multi` (Brave/Tavily/Exa via env keys) — without this, no tool is a GEO tool |
| `embedding_model` | str | `nomic-ai/nomic-embed-text-v1.5` FULL default; MiniLM LITE-only |
| `spacy_model` | str | spaCy NER checkpoint, auto-falls-back to an installed real model |

Enterprise inputs (all optional, validated by Pydantic v2 with junior-readable errors): `search_intent` (informational / transactional / comparison / research / local / qa), `query_templates`, `prompt_frames` × `personas` × `prompt_volume`, `content_feeds` (RSS/sitemaps), `serp_footprints` (`engine|label|url`), `entity_aliases` / `entity_domains` / `entity_weighting` / `ontology_aliases`, `chunk_tokens` / `chunk_overlap_tokens` / `target_entity_density` / `top_k_retrieval`, 10-engine `engine_matrix`, `gsc_credentials` / `ga4_property` / `drift_webhook_url`, `api_key` / `fetch_allowlist`, Ollama `ollama_base_url` / `ollama_model`, eval thresholds. Template with every field explained: `config.example.yaml`.

## Features

| # | Engine | Output |
|---|---|---|
| 1 | Zero-cost multi-source harvester (SearXNG + paid APIs → DDG fallback, Reddit + YouTube UGC core, live LLM answer harvester) | Documents with real URLs, hashes, latency, HTTP status |
| 2 | Local embeddings (nomic default, BGE-M3/Qwen3 ready) + SQLite cache + FAISS index | Semantic vector proximity 0–1 |
| 3 | Local spaCy NER + mention detection + co-occurrence graph | Entity counts, citation gaps |
| 4 | Hybrid retrieval (BM25 + dense RRF + bge-reranker-v2-m3 cross-encoder, fail-open) | Retrieval that mirrors production RAG |
| 5 | Proximity / citation-gap / invisibility / share-of-voice core | Leaderboard, pitch list, recommendations |
| 6 | Verification + freshness (headers, schema dates, liveness) | Honest 0–100 score; never fakes data |
| 7 | Transformer sentiment + persona × platform matrix + risk windows | Net sentiment −1…+1, verbatim danger quotes |
| 8 | Token density (real BPE) + displacement plan | Exact tokens-to-displace per window |
| 9 | Drift time-series + ETS-lite forecast + Slack alerts | Trend slopes, z-scores, anomalies |
| 10 | Poisoning / negative-SEO, E-E-A-T gate, entity-gain, citation-stealer, fan-out coverage | CRITICAL flags with fixes |
| 11 | Visibility score, citation funnel, prompt volumes, daily snapshots | C-suite + agency reporting |
| 12 | RAG brief + JSON-LD patch + action plan + `wp_drafts/` + Looker bundle + WebMCP manifests | Closed-loop execution |
| 13 | RAGAS-style eval gates + FactCheck fixes + EVAL v2 harness | Build fails on hallucinated math |
| 14 | GSC Gen-AI impressions + GA4 LLM-referral split (wired, `configured: false` without creds) | Real attribution, never synthesised |

## Key metrics

* **Semantic Vector Proximity (0–1)** — entity↔topic binding strength.
* **RAG Invisibility Index (%)** — high-relevance articles missing your brand while citing competitors.
* **Vector Share of Voice (%)** — your footprint in the retrieval corpus, overall + per AI engine.
* **Citation gap (linked / unlinked / omitted)** — how each entity is cited.
* **Visibility 0–100 + Position + Δ vs median** — the executive card.
* **Volatility (mean ± stdev) + citation decay** — answer stability week-over-week.
* **Net Sentiment (−1…+1)**, **token density + tokens-to-displace**, **freshness** (live %, median age), **poisoning risk + status**, **drift trend + anomaly flag**, **verification score / verified**.
* **High-Density Off-Page Targets** — URLs to pitch. **Prioritized Recommendations** — what to do Monday morning.

## Outputs

Every audit writes a self-contained folder (`ragevda_output/` or `web_output/jobs/<timestamp>-<hash>/`) under the 5-output contract — `report.json` (machine) · `dashboard.html` (human) · `corpus.duckdb` + `drift_timeseries.duckdb` (analyst) · `rag_content_brief.md` + `action_plan` + `wp_drafts/` (action) · Looker + WebMCP bundles. Legacy CSVs (`proximity_scores`, `entity_citation_summary`, `off_page_targets`, `recommendations`, `sources`, `verification`, `sentiment_audit`, `share_of_voice_heatmap`, `token_density_adjuster`, `poisoning_*`, `semantic_drift`, …) are archived under `_legacy/`.

Query DuckDB directly: `SELECT url, title, http_status, age_days FROM sources ORDER BY age_days;`

## Deploy (LITE vs FULL)

| | LITE (free 512 MB / any gadget) | FULL (paid 2GB+ / local) |
|---|---|---|
| Image | `Dockerfile.render` | `Dockerfile` |
| Deps | `requirements.render.txt` (CPU torch, no reranker/pandas/reportlab/faiss) | `requirements.txt` / `pyproject.toml` |
| Embeddings | MiniLM-90MB | nomic → BGE-M3 / Qwen3 |
| Boot / audit RSS | ~180–250 MB / ~380–450 MB | ~400 MB+ / ~1.8 GB |
| Serving | gunicorn 1 worker × 2 threads, model-free `/health` | gunicorn 1 worker × 8 threads |

Required env on Render: `RAGEVDA_LITE=1`, `RAGEVDA_ALLOW_FALLBACK=1`, `RAGEVDA_DISABLE_RERANKER=1`, `RAGEVDA_WORKERS=1` (all in `render.yaml`). Optional: `HF_TOKEN`, `RAGEVDA_API_KEY`, `BRAVE_API_KEY` / `TAVILY_API_KEY` / `EXA_API_KEY`, `AI_CRAWLER_LOG`, `GSC_CREDENTIALS` / `GA4_PROPERTY`. Free services sleep — `/health` must return `{"ok": true}` once awake. If the deploy URL 404s, the service was likely created manually: either create it as a Blueprint from `render.yaml` or set Dockerfile Path to `./Dockerfile.render` and redeploy.

## Docs

Deep dives live in `docs/` — start with the map, not the walls of text:

* `docs/SAMPLE_DASHBOARD.md` · `docs/TOUR.md` (60-sec GIF storyboard) · `docs/VOLATILITY.md` · `docs/EXEC_VERDICT.md`
* `docs/FEEDS_IMPORTER.md` · `docs/CRAWLER.md` · `docs/ATTRIBUTION_GUIDE.md` · `docs/PRIVACY.md` (our SOC 2 answer)
* `docs/EVAL_V2.md` · `EVAL.md` · `docs/PUBLISHING.md` (PyPI + GHCR) · `docs/EMBEDDINGS.md` · `docs/SERVING.md` (FastAPI-first) · `docs/SCOPE_2026.md` (what was demoted and why + US/EU/IN-BR nuance)
* `docs/GUIDE_FULL.md` — the complete pre-2.3.0 reference, preserved verbatim.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| SearXNG UNREACHABLE, fell back to DuckDuckGo | URL not listening / unresolvable | Point `searxng_base_url` at a live instance or accept the fallback (working as designed) |
| 401 / missing spaCy / embedding model | Not installed / cached | Tool auto-falls-back to a real local model; or `python -m spacy download …` / pre-cache the checkpoint |
| HTTP 403/401/402 fetch warnings | Paywalled / bot-blocked sites | Expected — skipped, only fetchable pages kept |
| `verified: false` / low score | Thin corpus, partial provenance | Honest low confidence, not a crash — widen topics/feeds |
| Old UI after updating | Server doesn't hot-reload | Restart `cli web`, hard-refresh (Ctrl+Shift+R) |
| Audit feels "stuck" | Slow hosts / big embedding batches | Watch the 45s heartbeat; narrow scope (`max_pages` 40–80, `crawl_depth` 10–20) or set `RAGEVDA_LITE=1` |
| Audit too slow overall | 200 pages × retries + CPU transformers | Triage config (~3–5 min) or add Brave/Tavily/Exa keys to skip dead-end fetches |

## Responsible use

Scores are model-derived estimates — decision support, then verify outreach manually. Keep concurrency small (default 8), honor robots.txt and each site's Terms, throttle when asked. Zero-cost search can rate-limit: for production volume run your own SearXNG or use file mode. Nothing leaves your machine; `require_real_models: true` guarantees no silent synthetic numbers.

## Roadmap / Contributing / Author / License

* Near-term: hosted sample dashboard, release artifacts with sample `report.json`, `pip install ragevda` + GHCR images, robots hardening, 60% coverage, EVAL v2 with hand labels. Full list: `ROADMAP.md`.
* Contributions welcome per `CONTRIBUTING.md`; security policy in `SECURITY.md`.
* Author: Dipak Jadhav ([@dipakjad1993](https://github.com/dipakjad1993)) — applied AI engineer building cost-aware, fully-local LLM systems. Star the repo if auditable AI visibility matters to you.
* License: MIT — use it, improve it, and stop buying low-tier links in a 2016 bubble.
