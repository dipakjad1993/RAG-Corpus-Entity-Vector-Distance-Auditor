# Embeddings — single default + latency table (2026)

**Default (FULL): `nomic-ai/nomic-embed-text-v1.5`** — 137M params, 8k context,
Apache-2.0, local-only. Chain: nomic → BGE-M3 / Qwen3-0.6B → MiniLM last resort.
SQLite cache keyed `sha1(model+chunk)`. FAISS IndexFlatIP with numpy fallback.

**LITE profile:** MiniLM-90MB REAL embeddings (never TF-IDF unless
`RAGEVDA_ALLOW_FALLBACK=1` is set explicitly + UNVERIFIED banner shown).

**Sentiment:** `tabularisai/multilingual-sentiment-analysis` default;
`cardiffnlp/twitter-roberta` legacy fallback only.

## Reference latency (fixed 125-doc Guardian corpus, CPU, batch 32)

| Model | Params | Ctx | p50 embed 125 docs | Cache-hit 2nd run | Note |
|---|---|---|---|---|---|
| nomic-embed-text-v1.5 | 137M | 8k | ~45–90s | ~2–5s | default FULL |
| BGE-M3 | 567M | 8k | ~2–4 min | ~3–6s | dense+sparse+ColBERT |
| Qwen3-Embedding-0.6B | 600M | 32k | ~2–5 min | ~3–6s | #1 MTEB small |
| MiniLM-L6-v2 | 22M | 512 | ~15–30s | ~1–2s | LITE default |
| TF-IDF fallback | — | — | ~2s | — | explicit opt-in only, UNVERIFIED |

Re-run on your box: `python -m ragevda.cli benchmark-embeddings -c config.yaml`.
