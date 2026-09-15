# Changelog

All notable changes to RAG-EVDA. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]
### Added
- v2.1.0 LITE profile: `Dockerfile.render` + `requirements.render.txt` +
  `render.yaml` (CPU-only torch, MiniLM-90MB, reranker/hybrid OFF, lazy
  reportlab + webapp imports, 1×2 gunicorn, model-free `/health`).
- 10-engine tracking matrix; `RunConfig.lite_profile()` / `full_profile()` /
  `apply_env_overrides()`.
- `analysis/visibility.py` (Visibility 0–100, Position, Mentions-vs-Citations,
  median delta), `analysis/fanout.py`, `analysis/citation_funnel.py`,
  `analysis/sentiment_matrix.py`, `analysis/crawler.py`,
  `eval/factcheck.py` (gate fixes), `reporting/action_plan.py`
  (+ `wp_drafts/`), `reporting/looker.py`, WebMCP manifests.
- GSC Generative-AI + GA4 Data API attribution wired (fail-open);
  responsive single-column mobile CSS; deeper `rag_content_brief.md`.

### Fixed
- Concurrent audits no longer cross-contaminate logs/progress (single-flight
  engine: one audit at a time, friendly busy message naming the running job).
- Light mode now re-renders every color (app-bar, console, focus rings used
  baked dark values); `color-scheme` added for native controls.
- M3 Expressive polish: Pixel-first type stack (`Google Sans` → bundled
  Roboto Flex fallback), 20–28px cards with hover lift, spring-eased buttons.
- Auto-Detect entity hygiene: camelCase splits, generic nouns (`Funding`),
  CTA phrases (`Discover …`), possessive fragments, and brand-stem overlap
  rejected from competitor suggestions; brand-family containment fixed.

## [1.3.0] — 2026-09-12 — Enterprise experience release

### Added
- Enterprise 2026 web UI: gradient hero with live detection stats, bento input
  grid covering all 11 enterprise fields, clickable 3-step flow
  (Inputs → Deep Analysis → Outputs), sticky run bar with explicit
  **Show Outputs** action, skeleton loaders, toast notifications,
  elapsed/percent progress with color-coded live logs, and an enterprise footer.
- Deep-research Auto-Detect: 45 s budget, expanded discovery scan
  (about-us/services/blog/news/feeds), extra live search passes
  (services/solutions/reviews/`{brand} vs`), verified Wikipedia footprint,
  full 12-template intent set, and evidence-scaled knobs — pre-fills all 11
  inputs plus `chunk_overlap_tokens` from live data.
- Issue-highlighting framework (`ragevda/reporting/issues.py`): every core
  engine and subfunction is scanned for real computed problems and surfaced as
  bold color-coded CRITICAL / HIGH RISK / WATCH / STRENGTH cards — a global
  "Issues requiring attention" summary on Step 2, per-engine banners on all 10
  deep-dive pages, and red/amber/green flagged rows in every key table.
  Deep-page engine tabs now highlight correctly.
- Enterprise PDF (`report.pdf`, ~17 pages): cover page with KPI cards, contents,
  captioned charts (proximity bands, citation pie, per-engine SoV, brand
  sentiment pie, priority-topic invisibility), tinted per-section issue callouts,
  red/amber color-coded metric cells, full analysis of all 10 engines plus
  poisoning/engine-matrix extensions, complete outputs, and an appendix with
  thresholds + methods glossary.
- Outputs hub (Step 3): 12-section verified report — executive verdict KPIs,
  all-11-inputs echo, competitive leaderboard, top-60 proximity, citation
  ledger, top-20 off-page targets, top-20 recommendations with rationale,
  token-density plan, sentiment audit, synthetic queries, drift, verification,
  and all 15 deliverable downloads.
- Stale-PDF auto-heal: the `/files/<job>/report.pdf` endpoint rebuilds any
  cached PDF older than the generator module, so layout updates can never
  leave users downloading yesterday's document.

### Fixed
- Material 3 token-name mismatch that broke light mode
  (`--m3-surface-low` vs `--m3-surface-container-low`); both palettes now emit
  identical token names plus missing on-container roles, dual
  `body.light`/`body[data-theme]` scoping, and theme-safe alert/table CSS.
- Hardcoded dark-only colors replaced with theme tokens (invisibility KPI,
  schedules/history accents).

## [1.2.0] — 2026-09-12 — Real-data hardening release

### Removed
- Every synthetic/demo path: `SmokeBrand`/`Acme` demo jobs and empty failed runs
  purged from history; fabricated deep-analysis provenance rows
  (`"200"/"fresh"/"0"/"True"` hardcodes) deleted — real `report.json` provenance only.
- Generic JSON-LD boilerplate (`sameAs: []`) replaced with competitor-aware real-data graph.
- Duplicate screenshots removed (SHA-256 verified unique); 5.4 MB hero PNG replaced
  with 752 KB WebP; gallery captions corrected so one image is never shown as two features.

### Fixed
- Co-occurrence graph always returning 0 (case mismatch on node keys).
- Per-mention BPE token spans (was `chars/4` estimate even with tokenizer loaded).
- PDF/narrative percent double-scaling (`18.1%` rendered as `1810%`, `100%` as `10000%`).
- PDF verification badge could never show `UNVERIFIED`; `PRIMARY_HEX` literal in PDF chips.
- Sentiment risk-window column reading wrong key (`text` vs real `snippet`).
- `search_intent` mismatch: web UI offered `commercial`/`navigational`, config rejected them.
- `all_aliases_for()` returning list-in-list; anchor matching now word-boundary regex.
- File-corpus docs no longer claim HTTP liveness (`http_status=0`, `live=False`,
  `source_type=file`); PDF ingestion added via `pypdf`.
- All `datetime.utcnow()` deprecations; scheduler ↔ web-run config parity
  (`require_real_models`, `use_llm`, `dedupe_near`, `max_pages`, chunking knobs,
  engine matrix); unknown-engine warning; tracking series key includes competitors.
- Pinned missing dependencies: `flask`, `transformers`, `huggingface_hub`,
  `tokenizers`, `reportlab`, `pypdf`.

## [1.1.0] — 2026-08-30
- Self-contained offline dashboard theme (embedded font, zero CDN).
- Deep-analysis pages per micro-engine; auto brand/business probe (`auto_probe`).
- Real Guardian audit screenshots (125 docs, `BAAI/bge-small-en-v1.5`).

## [1.0.0] — 2026-08-28
- Initial release: 4 local micro-engines (harvester, embeddings+NER, analysis,
  reporting), CLI + Web UI + scheduler, DuckDB storage, 22 output files.
