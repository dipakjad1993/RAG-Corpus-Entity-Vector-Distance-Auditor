# Changelog

All notable changes to RAG-EVDA. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2.2.0] — 2026-09-15 — Enterprise GEO-depth release

### Fixed
- Paid-API fan-out covers ALL queries: `multi_search_all()` (ThreadPool batch,
  RRF-merged, `RAGEVDA_FANOUT_QUERIES=20` cap) + concurrent fetching bounded by
  `max_pages`/`max_concurrency`. Previously only `queries[0]` reached
  Brave/Tavily/Exa.
- Scheduler tick race: due-set snapshotted under lock, callback runs outside
  the lock, `last_run`/`last_job` re-applied under lock (no double-fire).
- GEO-real defaults: `harvester: multi`, `answer_harvester: multi`;
  6 standard intents (commercial/navigational legacy-only); TikTok opt-in
  plugin (`ugc_tiktok: false`); `generate_llms_txt: false` (P2 hygiene).

### Added
- 10 P0 engines in `advanced`: `citation_reverse` (passage-BERT stealer,
  >0.88 steal), `fanout_coverage` (cluster map), `eeat` (gate, <50 CRITICAL),
  `entity_gain` (15+ entities/page scorer), `reddit_topics` (subreddit
  extractor), `media` (image/video/Merchant/GBP), `multilingual` (per-doc lang
  + geo gaps), `white_label` + `mcp_tools`, prompt volumes + daily snapshots +
  drift alerts in `tracking.py`, `probe_infer.py` + `deep_sections.py` splits.
- `docs/EMBEDDINGS.md`, `docs/SERVING.md`, `docs/SCOPE_2026.md`; CI
  `version-check` job; `config.example.yaml` synced to new defaults.
- Tests: `tests/test_enterprise_p0.py` (10 tests). Suite: 59 passed, 9 skipped.

## [2.1.1] — 2026-09-15 — Audit-always-completes release

### Fixed
- Audit no longer looks "stuck at X%": every pipeline phase now emits a named
  log marker (harvest plan → UGC → dedupe → corpus built → context → proximity
  → citation-gap → invisibility → recommendations → advanced → freshness →
  persist → CSV → dashboard), and the web progress bar maps each marker to a
  monotonic 6→98% stage.
- 45s heartbeat watchdog in the web worker: silent CPU/network phases
  (large embedding batches, one-time sentiment-model download, rate-limited
  harvest) log `still working: <stage> (<elapsed>s)` so the console and bar
  visibly prove liveness.
- Harvest time-box: `RAGEVDA_HARVEST_TIMEOUT` (default 480s) stops issuing new
  DDG queries on deadline and continues with collected candidates; fetch phase
  honors 2× deadline and keeps partial results. Per-empty-query fallbacks cut
  from 3 variants to 1 (each is a full network round-trip).
- UGC time-box: `RAGEVDA_UGC_TIMEOUT` (default 90s) with 5 seed queries per
  source (was 20/15/10); reddit → youtube → tiktok degrade gracefully on
  budget exhaustion instead of freezing the audit.

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
