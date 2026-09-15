# 2026 scope notes — what we demoted and why (Google May-15-2026 guide)

- **llms.txt / agent.json / mcp.json**: P2 hygiene for coding agents ONLY.
  Zero ranking/AIO effect per Google. `generate_llms_txt: false` default.
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
  informational / transactional / comparison / research / local / qa.
- **Cost honesty**: $0 base local; $0–50/mo optional for Brave/Tavily/Exa live
  answers. Data stays local except paid-API query strings.
