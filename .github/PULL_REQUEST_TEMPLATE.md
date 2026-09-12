## What changed

## Real-data checklist (required)

- [ ] No synthetic/demo numbers introduced (heuristics labelled as heuristics)
- [ ] Units explicit: fractions (`0..1`) vs percents (`0..100`), `_pct` vs `_pct100`
- [ ] `require_real_models=True` path hard-fails (no silent fallback)
- [ ] Screenshots (if any) are unique real-job captures with job ID + date caption

## Verification

- [ ] `make test` passes
- [ ] `make lint` passes
