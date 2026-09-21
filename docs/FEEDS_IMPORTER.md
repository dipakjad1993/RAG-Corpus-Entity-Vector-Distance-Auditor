# Feeds + footprints importer — your moat vs 15-prompt plans

Otterly Lite tracks 15 prompts. Your corpus is bounded only by
`max_search_queries` / `max_pages` + these two lists:

* **`content_feeds`**: competitor/industry RSS + sitemap URLs. The harvester
  (`ragevda/harvester/feeds.py`) ingests newly-published articles directly —
  real-time freshness on top of search. Start with 5–10 feeds:
  competitor blogs, industry pubs, your own changelog.
* **`serp_footprints`**: concrete AI-engine citation URLs, one per line as
  `engine|label|url` or bare URL (`_clean_url()` strips pasted Markdown).
  Use for the exact Perplexity/AIO/Copilot citations you want to displace.

Web UI: paste both lists into Step 1 (Auto-Detect proposes feeds from
sitemap/robots discovery). CLI: `config.example.yaml` lines 71–75.
Watch `harvest_stats` (queries / candidates / fetched) + `source_freshness.csv`
to confirm they landed. Ten good feeds beat a hundred thin queries.
