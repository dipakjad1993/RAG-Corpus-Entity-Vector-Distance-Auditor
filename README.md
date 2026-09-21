# RAG-EVDA — RAG Corpus Entity & Vector Distance Auditor

![CI](https://github.com/dipakjad1993/RAG-Corpus-Entity-Vector-Distance-Auditor/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![Local-only](https://img.shields.io/badge/LLM-100%25%20local-orange)
![Version](https://img.shields.io/badge/version-2.3.0-black)
[![Live demo](https://img.shields.io/badge/demo-live%20on%20Render-brightgreen)](https://rag-corpus-entity-vector-distance-auditor.onrender.com/)

> **Try it live:** https://rag-corpus-entity-vector-distance-auditor.onrender.com/ (full UI — 11 inputs, Auto-Detect, Deep Analysis, Outputs hub).
> **Static sample (no cold start):** `docs/sample_dashboard/` — see `docs/SAMPLE_DASHBOARD.md`. Tour storyboard: `docs/TOUR.md`.

> **A zero-cost, fully-local engine that decodes how AI search engines (ChatGPT, Gemini, Claude, Perplexity, Copilot, Grok, Meta AI, DeepSeek, Google AI Overviews, Google AI Mode) perceive your brand vs competitors inside a RAG corpus — and tells you exactly what to publish to change it.** No OpenAI / Ahrefs / Semrush keys. No data leaves your machine. Every number backed by URL + hash + latency. Version 2.3.0.

| | | |
|---|---|---|
| **125 docs** audited in the reference Guardian run | **$0** API cost, forever | **5-file bundle** per run (JSON + HTML + DuckDBs + brief + action plan + Looker) |

## Try it in 30 seconds (offline, no network)

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m ragevda.cli run -c examples/offline_demo/config.yaml
# → ./ragevda_output_offline_demo/dashboard.html (10 sample docs, real local models)
```

`pip install ragevda` + versioned GHCR images land on the next tagged release — see `docs/PUBLISHING.md`. Full 1,324-line reference preserved at `docs/GUIDE_FULL.md`.

## Proof, not promises (real Guardian run, 125 docs)

| Entity | Proximity | Highly-relevant docs | Mentions |
|---|---|---|---|
| The New York Times | **0.6487** | 7 | 34 |
| The Guardian | 0.6012 | 6 | **159** |
| BBC News | 0.6034 | 3 | 12 |

High volume, sub-optimal vector placement — exactly what black-box scores hide. Sources, hashes, latencies: `sources.csv` / `report.json`.

## Why not a black-box SaaS?

| | RAG-EVDA 2.3.0 | Profound / Peec / Otterly |
|---|---|---|
| Cost | $0 local | $29–$25k/mo |
| Data leaves machine | Never | Yes |
| Metric | Auditable vector math + DuckDB provenance | Proprietary score |
| Volatility | Mean ± stdev + citation decay (`docs/VOLATILITY.md`) | Single-sample dashboard |
| Fix loop | `action_plan` + `wp_drafts/` + FactCheck fixes | Export CSV, good luck |

2026 context: AIO on ~48% of queries, 62–83% of citations from outside organic top-10, Reddit ~22% of AI citations, unlinked mentions r≈0.7 vs links r≈0.2. Details: `docs/SCOPE_2026.md`.

## What's new in 2.3.0 (Razorfish-review release)

* **TL;DR Executive Verdict card** — Visibility · Position · Δ vs median on top of every dashboard (`docs/EXEC_VERDICT.md`).
* **Answer volatility + citation decay** — mean ± stdev over `answer_repeats`, week-over-week SoV decay (`docs/VOLATILITY.md`).
* **Full P0-engine dashboard** — visibility, fan-out, E-E-A-T gate, entity-gain, reddit topics, media, multilingual, crawler, attribution.
* **Real robots.txt enforcement** (`ragevda/harvester/robots.py`, fail-open) + **EVAL v2** hand-label harness (`docs/EVAL_V2.md`).
* **Slim README + docs split, FastAPI-first serving, gh-pages sample + PyPI/GHCR publish workflows.**

## Locked defaults (don't touch)

nomic-embed-text-v1.5 FULL (MiniLM LITE-only) · hybrid BM25+dense + bge-reranker-v2-m3 · `harvester: multi` + `answer_harvester: multi` · Reddit+YouTube core, TikTok opt-in · `require_real_models: true` · 6 standard intents · 10-engine matrix · `generate_llms_txt: false` (P2 hygiene — zero AIO effect per Google May-2026).

## Docs (start here, not in the old mega-README)

`docs/SAMPLE_DASHBOARD.md` · `docs/TOUR.md` · `docs/VOLATILITY.md` · `docs/EXEC_VERDICT.md` · `docs/FEEDS_IMPORTER.md` · `docs/CRAWLER.md` · `docs/ATTRIBUTION_GUIDE.md` · `docs/PRIVACY.md` · `docs/EVAL_V2.md` · `docs/PUBLISHING.md` · `docs/EMBEDDINGS.md` · `docs/SERVING.md` (FastAPI-first) · `docs/SCOPE_2026.md` (demotions + global nuance) · `EVAL.md` · `docs/GUIDE_FULL.md` (full reference).

## Serve / deploy

```bash
uvicorn ragevda.api:app --host 127.0.0.1 --port 9000  # enterprise: /health /jobs /docs
python -m ragevda.cli web --port 9000                  # local operator UI only
```

LITE (512 MB free tier): `Dockerfile.render` + `RAGEVDA_LITE=1`. FULL: `Dockerfile` (nomic + hybrid + reranker). Never run Flask + FastAPI on the same port.

## Outputs (5-file contract, legacy CSVs under `_legacy/`)

`report.json` · `dashboard.html` · `corpus.duckdb` + `drift_timeseries.duckdb` · `rag_content_brief.md` + `action_plan` + `wp_drafts/` · Looker bundle + WebMCP manifests.

MIT — use it, improve it. Full changelog: `CHANGELOG.md`.
