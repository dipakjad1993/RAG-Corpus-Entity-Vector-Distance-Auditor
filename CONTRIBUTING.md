# Contributing to RAG-EVDA

Thanks for your interest — contributions that keep every number **real and
verifiable** are welcome.

## Ground rules

1. **No synthetic data, ever.** New analysis modules must derive from the live
   harvested corpus + local models. If a value is a heuristic (weights, bands,
   thresholds), label it as such in code comments, docstrings, and UI text.
2. **`require_real_models=True` is the default path.** Any new model fallback must
   hard-fail under this flag and be covered by a test asserting the `RuntimeError`.
3. **Small atomic PRs.** One feature/fix per PR, with tests. See `EVAL.md` for how
   to validate against the offline demo corpus.

## Development setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
pip install pytest ruff         # dev tools (not shipped)
python -m spacy download en_core_web_sm
```

## Checks before opening a PR

```bash
make test    # fast unit tests — no network, no models
make lint    # ruff check
```

- New harvesters: add a fixture-based test under `tests/` (recorded HTML, never
  live network in CI).
- New metrics: document units explicitly — fractions (`0..1`) vs percents
  (`0..100`). The v1.2.0 `1810%` bug came from mixing these; `_pct` vs `_pct100`
  helpers exist in every reporting module for exactly this reason.
- Screenshots: must be unique captures from a real job (SHA-256 checked), captioned
  with job ID + date. Never reuse one image under two feature headings.

## Commit style

Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`.
Keep the history reviewable — the project's credibility depends on it.
