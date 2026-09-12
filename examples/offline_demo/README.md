# Offline demo — 10-document sample corpus

> **What this is:** a miniature *sample* corpus (fictional brand and articles)
> whose only job is to prove the pipeline runs end-to-end offline in <30 s:
> `file` harvester → real local embeddings/NER/sentiment → real `report.json` +
> `dashboard.html`. It is **not market data** — never cite its scores as a real
> audit. For a real audit, point `corpus_files` (or the live harvesters) at real
> sources.

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m ragevda.cli run -c examples/offline_demo/config.yaml
# open the printed output dir's dashboard.html
```

Expected: 10 docs harvested, `models_real: true`, proximity rows for 2 topics ×
3 entities, and `verified: false` with `live_score: 0.0` — file-corpus docs
honestly never claim HTTP liveness (score ≈ 92.0 on the reference machine).
