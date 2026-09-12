# Evaluation — how RAG-EVDA's numbers are validated

> Rule: every figure below is either (a) quoted verbatim from a real persisted
> `report.json`, or (b) explicitly labelled as a **protocol** (how to reproduce).
> No hand-waved precision/recall claims.

## 1. Reference run (real, reproducible inputs)

| Item | Value (from `report.json` meta) |
| ---- | ------------------------------- |
| Job | `web_output/jobs/20260830-094637-26b22b` |
| Brand / competitors | The Guardian vs NYT, BBC, WaPo, FT, Telegraph, Reuters |
| Harvest | 75 queries → 448 candidates → 303 fetched → 178 dedup → **125 docs** |
| Embedding | `BAAI/bge-small-en-v1.5` (local, offline) |
| NER | `en_core_web_sm` (local) |
| Sentiment | `cardiffnlp/twitter-roberta-base-sentiment-latest` (local) |
| Graph | 7 nodes / 18 edges / density 0.857 |
| Verification | score 72.0, `verified: false` (honest low-confidence flag: partial support) |

Spot checks that must hold on any re-run of the same corpus in `file` mode:

- `Digital Journalism & Independent Media`: Guardian proximity ≈ 0.60
  (6 highly-relevant docs, 159 mentions, `high` confidence) vs NYT ≈ 0.65.
- `mention_rate_pct` for The Guardian ≈ 28.0% (35/125 docs).
- Sentiment: Guardian net ≈ +0.27 (159 mentions), Reuters net ≈ −0.01 (162 mentions).

## 2. Module-level protocols (no network, no models)

`make test` runs the fast suite. Each test states its oracle:

| Test | Module | Oracle |
| ---- | ------ | ------ |
| `test_config_validation.py` | `RunConfig.validate` | placeholder/short/empty inputs raise `ValueError`; 7 intents accepted |
| `test_queries.py` | `search_queries` | every topic keeps its primary query under `max_search_queries` cap; order-preserving dedup |
| `test_mentions.py` | `NER.build_mention_patterns` + `find_mentions` | alias remapping attributes sub-brand hits to parent; word boundaries respected |
| `test_graph.py` | `CoOccurrenceGraph` | capitalized entities return non-zero `bind_strength` (regression test for the v1.2.0 case bug) |
| `test_reporting_math.py` | `_pct` vs `_pct100` | fractions scale (`0.181`→`18.1%`), already-percent passthrough (`18.1`→`18.1%`) |

## 3. Cost comparison (public pricing, verify at time of reading)

| Approach | Corpus cost | Model cost | Data leaves machine? |
| -------- | ----------- | ---------- | --------------------- |
| RAG-EVDA | $0 (DDG/SearXNG + Trafilatura) | $0 (local HF + spaCy) | No |
| Semrush / Ahrefs tier | ~$139–$499/mo subscription | included | Yes (queries to vendor) |
| AI-visibility SaaS (Profound, Peec, Otterly…) | ~$99–$999/mo | included | Yes (black-box score) |

RAG-EVDA's differentiator is not the price alone — it is **auditable retrieval
math** (proximity / invisibility / token-displacement) with full DuckDB
provenance, reproducible offline, vs a vendor score you cannot inspect.

## 4. Open eval gaps (roadmap, not claims)

- [ ] Hand-labeled citation-gap precision/recall on 50 docs (`EVAL v2`).
- [ ] RAGAS `faithfulness` / `context_precision` on `corpus.duckdb` vs this tool's
      retrieval flags, published win/tie/loss.
- [ ] Latency table MiniLM vs BGE-small vs MPNet on a fixed 125-doc corpus.
- [ ] Multilingual NER spot-check (`xx_ent_wiki_sm`).
