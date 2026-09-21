# AI-crawler analytics — Scrunch's moat, open-source

Scrunch's differentiator is seeing which AI bots fetch your pages, not just
which answers name you. Ours (`ragevda/analysis/crawler.py`, dashboard
section "AI-Crawler Analytics"):

* Point `AI_CRAWLER_LOG` at your access log
  (e.g. `/var/log/nginx/access.log`). Common/Combined format parsed for
  GPTBot, OAI-SearchBot, ClaudeBot (+anthropic-ai), PerplexityBot,
  Google-Extended, Bytespider.
* Report: total AI hits + per-bot counts + top-20 paths. Missing log ->
  explicit `{"configured": false}` with setup steps, never fake data.
* Pair with `harvester/robots.py` enforcement: allow GPTBot where you want
  citations; blocking it removes training + some citation paths. Measure
  first (`total_ai_hits` trend), then decide per-path.

Ops note: log-rotate safe (reads current file); for fleet-scale, ship logs
centrally and point the env var at the aggregate.
