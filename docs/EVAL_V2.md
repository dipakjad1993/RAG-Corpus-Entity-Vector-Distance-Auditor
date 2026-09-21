# EVAL v2 — hand-labeled citation-gap precision/recall

v1 gates (`pytest --geo`: faithfulness ≥ 0.75, answer relevancy ≥ 0.80,
context precision/recall ≥ 0.70) prove the math is self-consistent. v2 proves
it matches *human judgment*.

Protocol (`ragevda/eval/v2_protocol.py`, labels in
`ragevda/eval/labels_v2.sample.json`):

1. Sample 50 docs stratified across linked / unlinked / omitted per the
   `report.json` citation ledger.
2. Two annotators label each doc blind (`human` field); adjudicate disagreements.
3. Run `precision_recall(labels)` -> per-class precision/recall/F1 + macro F1
   + accuracy. Target: macro F1 ≥ 0.80 before claiming "citation-gap validated".
4. Compare against the RAGAS-style gate outputs on the same 50 docs; publish
   the notebook + confusion matrix in a release artifact.

The 5-row sample in-repo keeps CI green; your 50-row file stays private with
client data. No hand-waved "94% accurate" claims — show the matrix or do not
claim it.
