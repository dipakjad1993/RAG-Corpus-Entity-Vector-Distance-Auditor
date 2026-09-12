# Security Policy

## Design posture

RAG-EVDA is **fully local by design**: embeddings, NER, sentiment, storage, and
reporting all run on the operator's machine. No brand data, corpus text, or
credentials are sent to any third party. The only network traffic the tool
initiates is:

1. Public web harvesting (DuckDuckGo/SearXNG search + `httpx` page fetches with a
   standard browser User-Agent),
2. Optional first-run Hugging Face model downloads (cached afterwards; audit-time
   loads are offline via `HF_HUB_OFFLINE=1`),
3. Optional local Ollama endpoint (`http://localhost:11434` by default — never a
   cloud LLM API).

There are no API keys, tokens, or secrets in the codebase. `config.yaml` holds
only brand/topic names and model choices — still, `config.yaml` is git-ignored;
commit only `config.example.yaml`.

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 1.2.x   | :white_check_mark: |
| < 1.2.0 | :x:                |

## Reporting a vulnerability

Open a **private security advisory** on GitHub
(`Security` → `Report a vulnerability`) or email the maintainer. Please include:

- affected version (`python -m ragevda.cli --version`),
- reproduction steps (config + logs, redacting your brand names if sensitive),
- expected vs actual behaviour.

We aim to acknowledge within 72 hours and ship a fix or mitigation within
14 days for verified issues.

## Dependency hygiene

- `requirements.txt` / `pyproject.toml` pin minimum versions; run
  `pip-audit` before each release (`make audit`).
- Dependabot is enabled (`.github/dependabot.yml`) for pip + GitHub Actions.
- Heavy ML deps (`torch`, `transformers`, `spacy`) come from PyPI only — verify
  hashes in locked environments for production use.
