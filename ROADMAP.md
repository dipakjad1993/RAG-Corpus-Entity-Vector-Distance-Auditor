# Roadmap

## Next (v1.2.x — credibility)
- [ ] `examples/offline_demo` 10-doc file-mode corpus runnable in <30 s (shipped in v1.2.1).
- [ ] CI matrix Python 3.10/3.11/3.13 + `ruff` + `pytest` badge (shipped in v1.2.1).
- [ ] `gh-pages` branch serving a redacted sample `dashboard.html`.
- [ ] Release artifacts: sample `report.json` + `dashboard.html` attached to GitHub releases.

## Soon (v1.3 — depth)
- [ ] Split god-files: `analysis/auto_probe.py` (1629 L) → `probe_fetch/parse/infer`;
      `reporting/deep_analysis.py` (1444 L) → per-engine modules.
- [ ] Real `robots.txt` enforcement via `urllib.robotparser` in harvest fetch paths
      (currently politeness is concurrency-capped only; README claims softened meanwhile).
- [ ] `threading.Lock` around web `JOBS` registry + scheduler callback (known limitation).
- [ ] Coverage to 60% (harvester fallback, drift math, poisoning heuristics).
- [ ] EVAL v2: hand-labeled citation-gap precision/recall (50 docs) + RAGAS comparison.

## Later (v1.4+ — reach)
- [ ] PyPI publish (`pip install ragevda`) + versioned Docker images (GHCR).
- [ ] Multilingual NER (`xx_ent_wiki_sm`) + language auto-detect per document.
- [ ] SearXNG + Ollama one-command stack (`docker compose --profile full`).
- [ ] Fly.io / Hugging Face Spaces hosted demo (redacted corpus only).
- [ ] Near-duplicate cosine dedup honouring `near_dup_threshold` (currently exact-only).
