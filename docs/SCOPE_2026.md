# 2026 scope notes — what we demoted and why (Google May-2026 guide)

- **llms.txt / agent.json / mcp.json**: P2 hygiene for coding agents ONLY.
  Zero ranking/AIO effect per Google (Mueller: "like the keywords meta tag";
  no engine documents consulting it for retrieval). `generate_llms_txt: false`
  default. Kept lean for `navigator.modelContext` agent surface — never sold
  as a ranking lever. Full `llms-full.txt`/MCP outputs still emitted per run
  for agent tooling, under `report.json` provenance, not as SEO promises.
- **Chunking 512/64**: retriever simulator for modeling, NOT a ranking lever.
  Google: "no requirement to break into tiny pieces." We report passage +
  answer-first guidance instead of token-count magic.
- **MiniLM + TF-IDF**: MiniLM = LITE profile only; TF-IDF requires
  `RAGEVDA_ALLOW_FALLBACK=1` + UNVERIFIED banner. Never marketed as equal.
- **Synthetic queries**: LEGACY. Forward-tracked prompt library
  (frames × personas × geo × volume) is default.
- **TikTok scraper**: optional plugin (`ugc_tiktok: false` default). YouTube +
  Reddit are core; TikTok via paid SERP API only.
- **Commercial/navigational intents**: legacy back-compat only. Standard set:
  informational / transactional / comparison / research / local / qa
  (commercial duplicates transactional; navigational never triggers AIO).
- **Cost honesty**: $0 base local; $0–50/mo optional for Brave/Tavily/Exa live
  answers. Data stays local except paid-API query strings.

## Global nuance (2026 surfaces differ — one playbook does not fit all)

- **US**: AIO (~48% queries) + ChatGPT Shopping + AI Mode journey modules.
  Win via entity density (20.6% cited baseline) + freshness (<30d = 3.2x).
- **EU/DE**: Peec country; GDPR-local hosting is the closer. Our local-only
  (no subprocessor, DuckDB in-VPC) beats SaaS SOC 2 narratives. Track
  `geo_variants` + `languages` per prompt (see `multilingual` report).
- **IN/BR + mobile-first**: YouTube transcripts + Meta AI matter more than
  Reddit. Our YouTube path is core; Reddit weight drops per
  `sentiment_matrix` platform split. 77% mobile zero-click → optimize for
  citation, not the click.
