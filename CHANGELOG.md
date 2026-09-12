# Changelog

All notable changes to RAG-EVDA. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
