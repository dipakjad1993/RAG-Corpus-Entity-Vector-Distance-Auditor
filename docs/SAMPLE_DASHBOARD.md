# Sample dashboard — try before Render wakes up

Free-tier Render sleeps (~60s cold start). This page is the instant proof:

* **Live demo (full UI):**
  https://rag-corpus-entity-vector-distance-auditor.onrender.com/
* **Static redacted sample (this repo, always awake):**
  `docs/sample_dashboard/` — generated from the offline demo
  (`python -m ragevda.cli run -c examples/offline_demo/config.yaml`),
  then copied here redacted. Open `dashboard.html` locally; no server needed.
* **Publish to gh-pages (maintainer):**
  `python tools/publish_sample.py --job ragevda_output_offline_demo`
  copies `dashboard.html` + `report.json` (hashes kept, private URLs redacted
  when flagged) into `docs/sample_dashboard/`. The `gh-pages.yml` workflow
  serves that folder on every push to `main`.

Reference numbers (Guardian live run `web_output/jobs/20260830-094637-26b22b`,
125 docs): NYT 0.6487 vs Guardian 0.6012 on Digital Journalism despite 159 vs
34 mentions — high volume, sub-optimal vector placement. Every number backed
by URL + hash + latency in `sources.csv` / `report.json`.
