# TL;DR Executive Verdict — the LinkedIn screenshot card

One card, five numbers, one sentence. Computed in
`ragevda/reporting/verdict.py` from REAL report evidence only:

* **Visibility 0–100** = `100*(0.7*mean_proximity + 0.3*mention_share)`
* **Position** = rank vs competitors; **Δ vs median** = brand − median
  competitor visibility (Semrush-style)
* **Mentions vs linked-citations** split from the citation ledger
* **Invisibility % / SoV %** composites

Verdict ladder: **WINNING** (vis ≥ 60, invis ≤ 25, Δ ≥ 0) /
**COMPETITIVE** (vis ≥ 40, invis ≤ 50) / **CRITICAL** (E-E-A-T < 50 or
invis ≥ 70) / **AT RISK** otherwise. Rendered top of every `dashboard.html`
with red/amber/green tone + the one-sentence CMO summary.
