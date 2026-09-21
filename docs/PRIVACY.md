# Privacy story — our SOC 2 answer without a SOC 2 audit

We cannot afford a SOC 2 audit. We do not need one for the core promise:

* **No data leaves your VPC.** Embeddings, NER, sentiment, DuckDB, HTML/PDF —
  all local. The only network calls are your own harvest fetches + optional
  paid answer APIs (query strings only, keys via env, never committed).
* **No subprocessors.** No black-box score vendor sees your brand list.
* **SSRF guard** on every fetch (no private/loopback hosts, redirect chain
  validated, optional `fetch_allowlist`), **robots.txt** enforced via
  `ragevda/harvester/robots.py`, per-IP rate limiting, API-key auth + CSRF
  double-submit when `RAGEVDA_API_KEY` is set, non-root Docker, loopback bind
  by default.
* **LITE profile** (`RAGEVDA_LITE=1`) keeps PII in-region on a 512 MB box;
  TF-IDF fallback requires explicit `RAGEVDA_ALLOW_FALLBACK=1` + renders an
  UNVERIFIED banner — never silent degradation.

For regulated YMYL (medical/legal/financial — filtered hard in AI Mode),
this is *stronger* than a SaaS SOC 2: there is no vendor copy of your data
to breach. EU/DE buyers: local hosting = GDPR-friendly by architecture.
