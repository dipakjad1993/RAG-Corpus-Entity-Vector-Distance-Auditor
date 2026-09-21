# 60-second tour — storyboard for the GIF / Loom (No GIF, no star)

Record once, put the GIF above the fold in README + `docs/SAMPLE_DASHBOARD.md`:

1. **0–10s — Paste URL, hit Auto-Detect.** Homepage + robots/sitemap/about/
   JSON-LD + live topic/competitor searches pre-fill all 11 inputs.
2. **10–30s — Run Full Audit.** Named phase markers move the bar 6→98%
   (harvest plan → UGC → dedupe → corpus → proximity → citation-gap →
   invisibility → recommendations → advanced → persist); 45s heartbeat proves
   liveness on slow nets. Time-boxes: `RAGEVDA_HARVEST_TIMEOUT` 480s,
   `RAGEVDA_UGC_TIMEOUT` 90s.
3. **30–45s — Deep Analysis.** Global CRITICAL / HIGH RISK / WATCH / STRENGTH
   cards + per-engine banners + red/amber/green rows.
4. **45–60s — Show Outputs.** TL;DR verdict card (Visibility · Position ·
   Δ vs median) + leaderboard + pitch list + all downloads.

Capture at 1280px, light mode, real Guardian offline demo
(`examples/offline_demo`, <30s, no network). Export GIF < 5 MB
(`ffmpeg -vf fps=10,scale=960:-1`). Voiceover script lives in
`assets/demo_script.md` (add your Loom link here when recorded).
