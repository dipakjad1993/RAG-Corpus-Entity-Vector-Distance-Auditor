"""RAG-EVDA local web application.

A self-contained Flask app that provides:

* A **start page** with the five Section-2 inputs (brand, topics, competitors,
  crawl depth, locality) plus an advanced panel (harvester choice, models).
* **Real-time tracking** via polling: on submit it launches the full local
  pipeline (live DuckDuckGo / SearXNG / file harvesting, local embeddings,
  spaCy NER, co-occurrence graph, proximity / citation-gap / invisibility
  analysis) and the browser polls for progress, a progress bar, an elapsed
  timer and live log lines.
* **Real outputs** — when the run finishes it serves the generated dashboard,
  CSVs and JSON from the job's output directory.
* **Light / dark theme toggle** (persisted in localStorage).

Run with:
    python -m ragevda.webapp            # http://127.0.0.1:8765
or:
    python -m ragevda.cli web
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List

from flask import Flask, Response, request, send_from_directory, redirect

from .tracking import (load_runs, brands, runs_for_brand, diff_runs,
                        trend_chart, per_topic_trend_chart)
from .scheduler import Scheduler, Schedule


def _lazy_narrative():
    from .reporting import narrative as _n
    return _n


def _lazy_deep():
    from .reporting import deep_analysis as _d
    return _d


def _lazy_style():
    from .reporting.theme import get_style as _g
    return _g

logger = logging.getLogger("ragevda.webapp")


def _load_job_data(job: str):
    """Load a finished job's report.json, or None if missing/unreadable."""
    p = os.path.join(WEB_OUTPUT, "jobs", job, "report.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None

JOBS: Dict[str, Dict] = {}
JOBS_LOCK = threading.Lock()  # guards JOBS create/update/read across worker threads
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_OUTPUT = os.path.join(ROOT, "web_output")
SCHEDULER = Scheduler()

# Persistent job store (SQLite) mirrors JOBS so jobs survive restarts and N
# users can queue concurrently. JOBS dict remains as a live-view cache.
try:
    from . import jobs_store as _jobs_store
    _jobs_store.init(WEB_OUTPUT)
    _USE_JOB_STORE = True
except Exception:  # noqa: BLE001
    _USE_JOB_STORE = False

# Bounded worker pool (replaces unbounded per-job threads + single-flight).
import concurrent.futures as _fut
_WORKERS = int(os.environ.get("RAGEVDA_WORKERS", "1"))
_POOL = _fut.ThreadPoolExecutor(max_workers=max(1, _WORKERS))

try:
    _WEB_STYLE = _lazy_style()("webapp")
except Exception:  # theme module pulls zero heavy deps; guard anyway
    _WEB_STYLE = ""

WEB_STYLE = _WEB_STYLE

# Order matters: first matching keyword wins.
# Note: the pipeline's own "audit complete" log line must NOT be mapped to 100 —
# it can arrive while other worker threads are still flushing logs (which would
# leave the bar at 100% + a stale stage while work continues). Only the wrapper
# in _run_job() sets 100, strictly after run() returned.
_PROGRESS_RULES = [
    ("wrote HTML dashboard", 98, "Generating HTML dashboard"),
    ("wrote CSV", 96, "Generating CSV reports"),
    ("wrote JSON report", 94, "Generating JSON report"),
    ("audit complete", 99, "Finalizing results"),
    ("context built", 85, "Building graphs & metrics"),
    ("embedded", None, "Embedding documents"),  # special-cased below
    ("embedding", 80, "Embedding documents"),
    ("building analysis context", 75, "Analyzing semantics"),
    ("harvested", 72, "Corpus built"),
    ("fetched", None, "Fetching pages"),          # special-cased below
    ("fetching", 42, "Fetching pages"),
    ("capped candidates", 38, "Preparing fetch list"),
    ("raw results", None, "Harvesting search results"),  # special-cased below
    ("starting audit", 6, "Initializing pipeline"),
]


def _progress_from_msg(job: Dict, msg: str) -> None:
    if job.get("status") == "done":
        # a late/flushed worker log must never move the bar off 100 or flip
        # the stage after the audit already finished
        return
    low = msg.lower()
    prog = job.get("progress", 0)
    stage = job.get("stage", "")
    for keyword, value, label in _PROGRESS_RULES:
        if keyword.lower() in low:
            if keyword == "fetched":
                m = re.search(r"fetched (\d+)/(\d+)", msg)
                if m:
                    x, y = int(m.group(1)), int(m.group(2)) or 1
                    job["progress"] = min(70, 42 + int(x / y * 28))
                job["stage"] = f"Fetching pages ({m.group(1)}/{m.group(2)})" if m else "Fetching pages"
                return
            if keyword == "raw results":
                job["progress"] = min(35, prog + 3)
                job["stage"] = "Harvesting search results"
                return
            if keyword == "embedded":
                m = re.search(r"embedded (\d+)/(\d+)", msg)
                if m:
                    x, y = int(m.group(1)), int(m.group(2)) or 1
                    job["progress"] = min(89, 80 + int(x / y * 9))
                job["stage"] = "Embedding documents"
                return
            if value is not None:
                job["progress"] = max(prog, value)
                job["stage"] = label
                return
    # unknown lines keep current progress


# ---------------------------------------------------------------------------
# Form helpers — explicit boolean parsing (unchecked is not explicit false)
# ---------------------------------------------------------------------------
def _parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    low = str(value).strip().lower()
    if low in ("1", "true", "on", "yes", "checked"):
        return True
    if low in ("0", "false", "off", "no", ""):
        return False
    return True


def _parse_float(value, default: float) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _parse_int(value, default: int) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Live log handler -> per-job log list (for polling)
# ---------------------------------------------------------------------------
class _JobLogHandler(logging.Handler):
    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with JOBS_LOCK:
                j = JOBS.get(self.job_id)
                if not j:
                    return
                j["logs"].append(msg)
                if len(j["logs"]) > 800:
                    j["logs"] = j["logs"][-800:]
                _progress_from_msg(j, msg)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Start page HTML
# ---------------------------------------------------------------------------
INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#141218" id="metaTheme">
<meta name="description" content="RAG-EVDA — enterprise local vector intelligence for AI-search visibility. Zero-cost, verified, real-time.">
<title>RAG-EVDA — RAG Corpus Entity & Vector Distance Auditor</title>
<style>
__M3_STYLE__
/* ---- enterprise web-app layer (2026 Pixel / M3 Expressive) ---- */
.m3-app-inner{max-width:1280px}
.card{background:var(--m3-surface-container-low); border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-m); padding:20px 22px; margin-bottom:16px; box-shadow:var(--m3-shadow-1);
  transition:transform .3s var(--m3-ease), box-shadow .3s var(--m3-ease), background-color .35s, border-color .35s}
.card:hover{box-shadow:var(--m3-shadow-2)}
.card label.m3-fieldlabel,.card label{display:block; font-weight:600; font-size:13px; margin:0 0 6px; color:var(--m3-on-surface)}
.card .hint{color:var(--m3-on-surface-variant); font-size:12.5px; margin:-2px 0 12px; line-height:1.65}
.card .row{display:flex; gap:12px; margin-top:12px; flex-wrap:wrap; align-items:flex-end}
.m3-nav a.on{background:var(--m3-secondary-container); color:var(--m3-on-secondary-container)}
.nav-btns{display:flex; gap:12px; margin-top:20px; flex-wrap:wrap}
.err{color:var(--m3-error)}
iframe{width:100%; height:82vh; border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-m); background:var(--m3-surface-container-lowest); box-shadow:var(--m3-shadow-2); color-scheme:dark}
body.light iframe,body[data-theme="light"] iframe{color-scheme:light}
.m3-adv{display:inline-flex; align-items:center; gap:8px; background:none; border:none;
  color:var(--m3-primary); font-weight:700; font-size:14px; cursor:pointer; padding:6px 0; font-family:var(--m3-font)}
#result{margin-top:20px}
/* hero / bento / enterprise */
.hero{position:relative; overflow:hidden; border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-l); padding:30px 30px 26px; margin:6px 0 20px;
  background:linear-gradient(135deg, color-mix(in srgb, var(--m3-primary) 16%, transparent), transparent 55%),
  linear-gradient(225deg, color-mix(in srgb, var(--m3-tertiary) 13%, transparent), transparent 50%),
  var(--m3-surface-container-low); box-shadow:var(--m3-shadow-2)}
.hero h1{font-size:clamp(26px,3.6vw,38px); line-height:1.08; letter-spacing:-.7px; margin:0 0 8px; font-weight:800}
.hero h1 .grad{background:linear-gradient(90deg,var(--m3-primary),var(--m3-tertiary));
  -webkit-background-clip:text; background-clip:text; color:transparent}
.hero p{color:var(--m3-on-surface-variant); font-size:15px; line-height:1.7; max-width:900px; margin:0 0 14px}
.trust-row{display:flex; gap:8px; flex-wrap:wrap; margin-top:6px}
.bento{display:grid; gap:16px; grid-template-columns:repeat(12,1fr); margin:0 0 6px}
.bento .card{margin-bottom:0}
.span7{grid-column:span 7}.span5{grid-column:span 5}.span6{grid-column:span 6}
.span4{grid-column:span 4}.span8{grid-column:span 8}.span12{grid-column:span 12}
@media(max-width:960px){.span7,.span5,.span6,.span4,.span8{grid-column:span 12}}
.field-head{display:flex; align-items:center; gap:12px; margin-bottom:4px}
.field-ico{width:38px; height:38px; border-radius:12px; flex:0 0 auto; display:flex; align-items:center; justify-content:center;
  font-size:18px; background:var(--m3-primary-container); color:var(--m3-on-primary-container); box-shadow:var(--m3-shadow-1)}
.field-num{margin-left:auto; font-size:11px; font-weight:800; letter-spacing:.8px; color:var(--m3-on-surface-variant);
  background:var(--m3-surface-container-high); border:1px solid var(--m3-outline-variant); padding:3px 10px; border-radius:99px}
.fill-badge{display:none; font-size:11px; font-weight:800; color:var(--m3-on-tertiary-container);
  background:var(--m3-tertiary-container); padding:3px 10px; border-radius:99px; margin-left:8px}
.fill-badge.show{display:inline-block; animation:pageIn .4s var(--m3-ease)}
.skel{position:relative; overflow:hidden; background:var(--m3-surface-container-high); border-radius:12px; min-height:18px}
.skel::after{content:""; position:absolute; inset:0; transform:translateX(-100%);
  background:linear-gradient(90deg, transparent, color-mix(in srgb, var(--m3-primary) 22%, transparent), transparent);
  animation:shimmer 1.4s infinite}
@keyframes shimmer{to{transform:translateX(100%)}}
#toasts{position:fixed; right:18px; bottom:18px; z-index:99; display:flex; flex-direction:column; gap:10px; max-width:min(420px,90vw)}
.toast{background:var(--m3-surface-container-highest); color:var(--m3-on-surface); border:1px solid var(--m3-outline-variant);
  border-radius:16px; padding:12px 16px; box-shadow:var(--m3-shadow-3); font-size:13px; animation:pageIn .35s var(--m3-ease)}
.toast.ok{border-color:var(--m3-tertiary)} .toast.bad{border-color:var(--m3-error)}
.run-bar{position:sticky; bottom:14px; z-index:15; display:flex; gap:10px; align-items:center; flex-wrap:wrap;
  background:color-mix(in srgb, var(--m3-surface-container) 92%, transparent); backdrop-filter:blur(12px);
  border:1px solid var(--m3-outline-variant); border-radius:20px; padding:12px 14px; box-shadow:var(--m3-shadow-2); margin-top:16px}
.stat-strip{display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); margin:14px 0 4px}
.stat-strip .m3-kpi{padding:14px 16px} .stat-strip .m3-kpi .v{font-size:22px}
.ent-footer{margin-top:26px; padding-top:18px; border-top:1px solid var(--m3-outline-variant);
  color:var(--m3-on-surface-variant); font-size:12.5px; line-height:1.7; display:flex; gap:14px; flex-wrap:wrap; justify-content:space-between}
kbd.m3-code{font-family:var(--m3-font)}
/* ---- enterprise alignment / formatting hardening ---- */
.m3-app-inner{margin:0 auto; padding:0 20px; width:100%; box-sizing:border-box}
.m3-container{max-width:1280px; margin:0 auto; padding:20px; box-sizing:border-box}
.m3-app-bar{position:sticky; top:0; z-index:50; backdrop-filter:blur(12px)}
.m3-app-bar .m3-app-inner{display:flex; align-items:center; gap:14px; padding-top:10px; padding-bottom:10px}
.m3-nav{display:flex; gap:8px; margin-left:auto; align-items:center; flex-wrap:wrap}
.m3-nav a{padding:8px 14px; border-radius:99px; text-decoration:none; font-weight:700; font-size:13px; white-space:nowrap}
.m3-input,.m3-select,textarea.m3-input,input.m3-input{width:100%; box-sizing:border-box; text-align:left}
table{width:100%; border-collapse:collapse; table-layout:auto}
th,td{padding:10px 12px; text-align:left; vertical-align:top; font-size:13px}
th{white-space:nowrap}
tr:nth-child(even) td{background:color-mix(in srgb, var(--m3-surface-container-high) 45%, transparent)}
.verified-badge,.estimate-badge{display:inline-block; font-size:11px; font-weight:800; letter-spacing:.4px; padding:3px 10px; border-radius:99px; margin:2px 4px 2px 0}
.verified-badge{background:color-mix(in srgb, #1abc9c 22%, transparent); border:1px solid #1abc9c}
.estimate-badge{background:color-mix(in srgb, #e67e22 20%, transparent); border:1px solid #e67e22}
.steps{display:flex; gap:8px; flex-wrap:wrap; margin:12px 0}
.steps .step{flex:1 1 180px; padding:10px 14px; border-radius:14px; border:1px solid var(--m3-outline-variant); font-size:13px; font-weight:700}
.steps .step.active{background:var(--m3-primary-container); color:var(--m3-on-primary-container)}
@media(max-width:720px){.m3-app-bar .m3-app-inner{flex-wrap:wrap}.hero{padding:22px 18px}th,td{font-size:12px; padding:8px}}
@media(max-width:768px){.bento{grid-template-columns:1fr}.bento .card{grid-column:span 12}}
img,canvas,svg{max-width:100%;height:auto} img[loading]{content-visibility:auto}
body{font-family:var(--m3-font,Google Sans,Roboto Flex,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif)}
</style></head>
<body>
<div class="m3-app-bar"><div class="m3-app-inner">
  <div class="m3-logo">EV</div>
  <div class="m3-title">RAG-EVDA
    <small>RAG Corpus Entity &amp; Vector Distance Auditor · Enterprise 2026</small>
  </div>
  <nav class="m3-nav">
    <a href="/" class="on">Audit</a>
    <a href="/history">History &amp; Trends</a>
    <a href="/schedules">Schedules</a>
  </nav>
  <button class="m3-btn outlined" id="themeBtn" title="Toggle dark / light (Material 3)">Theme</button>
</div></div>

<div class="m3-container">
<div class="hero">
  <h1>AI-search visibility, <span class="grad">measured in vector space.</span></h1>
  <p>Local, zero-cost, fully verified vector intelligence. Paste any brand or website URL, hit
  <b>Auto-Detect Deep Research</b> — the tool performs live multi-source reconnaissance and pre-fills
  <b>all 11 enterprise inputs</b> with real, verified, real-time data. Then <b>Run Full Audit</b> executes
  all <b>10 micro-engines</b> (harvest → embeddings → NER graphs → citation gaps → chunking → drift →
  LLM briefs → sentiment → synthetic queries → token density) and <b>Show Outputs</b> delivers the
  in-depth competitive report. No OpenAI / Ahrefs / Semrush keys. 2026 Pixel type · Material 3 Expressive · fluid navigation.</p>
  <div class="trust-row">
    <span class="m3-chip"><b>100%</b> local &amp; zero-cost</span>
    <span class="m3-chip"><b>11</b> enterprise inputs</span>
    <span class="m3-chip"><b>10</b> micro-engines</span>
    <span class="m3-chip"><span class="verified-badge">VERIFIED</span> real-time evidence</span>
    <span class="m3-chip"><span class="estimate-badge">ESTIMATE</span> engine/poisoning/queries = triage only</span>
    <span class="m3-chip"><b>M3</b> dark / light perfected</span>
  </div>
  <div class="stat-strip" id="heroStats">
    <div class="m3-kpi"><div class="v" id="hsTopics">—</div><div class="l">Topics detected</div></div>
    <div class="m3-kpi"><div class="v" id="hsComps">—</div><div class="l">Competitors mapped</div></div>
    <div class="m3-kpi"><div class="v" id="hsDepth">—</div><div class="l">Crawl depth</div></div>
    <div class="m3-kpi"><div class="v" id="hsLocality">—</div><div class="l">Locality signal</div></div>
  </div>
</div>

<div class="step-wrap" role="tablist" aria-label="Audit stages">
  <div class="step active" id="step1" role="tab" tabindex="0" onclick="goStep('inputs')"><span class="num">1</span> Inputs · 11 fields</div>
  <div class="step-sep"></div>
  <div class="step" id="step2" role="tab" tabindex="0" onclick="goStep('features')"><span class="num">2</span> Deep Analysis · 10 engines</div>
  <div class="step-sep"></div>
  <div class="step" id="step3" role="tab" tabindex="0" onclick="goStep('outputs')"><span class="num">3</span> Outputs · verified report</div>
</div>

<div id="page-inputs" class="page active">
<form id="auditForm">
  <div class="card">
    <div class="field-head"><div class="field-ico"></div>
      <label class="m3-fieldlabel" style="margin:0">1) Target Brand Name / Website URL — Deep-Research Entry Point</label>
      <span class="field-num">INPUT 01 · REQUIRED</span><span class="fill-badge" id="fb-brand">AUTO-FILLED</span></div>
    <div class="hint">Paste a brand <b>or any website / URL</b> (e.g. <span class="m3-code">https://yoursite.com</span>) then click
      <b>Auto-Detect Deep Research</b>. The tool fetches the live homepage in real time, scans robots / sitemap / about / products,
      reads schema.org JSON-LD + feeds + headings, runs budgeted live web searches for topics / competitors / HQ country, detects
      language + local Ollama / SearXNG services, scores search intent, and <b>fills all 11 input groups below</b> with verified live evidence. Nothing is invented.</div>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <input type="text" name="target_brand" placeholder="YourBrand or https://yoursite.com" required class="m3-input" style="flex:1;min-width:260px">
      <button type="button" class="m3-btn" id="probeBtn">Auto-Detect Deep Research</button>
    </div>
    <div id="probeStatus" class="hint" style="margin-top:8px;display:none"></div>
    <div id="probeStages" class="hint" style="display:none; margin-top:6px"></div>
  </div>

  <div class="bento">
  <div class="card span7">
    <div class="field-head"><div class="field-ico"></div>
      <label class="m3-fieldlabel" style="margin:0">2) Target Industry Topics / Concepts</label>
      <span class="field-num">INPUT 02 · 3–10+</span></div>
    <div class="hint">High-value contextual topics &amp; seed keywords auto-extracted from live headings, meta keywords, JSON-LD categories, nav labels, news-sitemap headlines &amp; real search titles. One per line or comma-separated — no limit.</div>
    <textarea name="industry_topics" class="m3-input" placeholder="your primary industry topic&#10;your secondary topic&#10;your tertiary topic" required></textarea>
  </div>

  <div class="card span5">
    <div class="field-head"><div class="field-ico"></div>
      <label class="m3-fieldlabel" style="margin:0">3) Competitor Entities</label>
      <span class="field-num">INPUT 03 · 2–5+</span></div>
    <div class="hint">Direct rivals mined from on-page comparisons + live “competitors / alternatives / rivals” searches, sanitized against generic words. One per line.</div>
    <textarea name="competitor_entities" class="m3-input" placeholder="CompetitorA&#10;CompetitorB&#10;CompetitorC" required></textarea>
  </div>
  </div>

  <div class="m3-field-grid">
    <div class="card">
      <div class="field-head"><div class="field-ico">≡</div>
        <label class="m3-fieldlabel" style="margin:0">4) Crawl Depth Parameter</label>
        <span class="field-num">INPUT 04</span></div>
      <div class="hint">Pages / results per query (Top 50 / Top 100). Auto-Detect scales this from real sitemap size &amp; news velocity.</div>
      <input type="number" name="crawl_depth" value="50" min="1" max="200" class="m3-input">
    </div>
    <div class="card">
      <div class="field-head"><div class="field-ico"></div>
        <label class="m3-fieldlabel" style="margin:0">5) Target Locality / Geo Target</label>
        <span class="field-num">INPUT 05 · OPTIONAL</span></div>
      <div class="hint">Region / country code (US, UK, Detroit). Detected from geo meta, hreflang, currency, city &amp; TLD signals.</div>
      <input type="text" name="locality" placeholder="US" class="m3-input">
    </div>
  </div>

  <div class="card">
    <button type="button" class="m3-adv" id="advToggle"> Enterprise inputs 6–11 + engine tuning (auto-filled — review &amp; expand)</button>
    <div id="advPanel" style="margin-top:14px;">
      <div class="m3-field-grid">
        <div>
          <label class="m3-fieldlabel">Harvester</label>
          <select name="harvester" class="m3-input">
            <option value="multi">Multi fan-out (SearXNG + Brave/Tavily/Exa + UGC — recommended)</option>
            <option value="duckduckgo" selected>DuckDuckGo (live, free — fallback only)</option>
            <option value="searxng">SearXNG (self-hosted)</option>
            <option value="answers">Answers only (needs paid keys)</option>
            <option value="file">Local corpus folder</option>
          </select>
          <label class="m3-check" style="margin-top:10px">
            <input type="checkbox" name="prefer_searxng"> Prefer SearXNG (use my SearXNG URL as the primary live search when set)
          </label>
        </div>
      </div>
      <div class="m3-field-grid">
        <div>
          <label class="m3-fieldlabel">SearXNG base URL</label>
          <input type="text" name="searxng_base_url" placeholder="http://localhost:8080" class="m3-input">
        </div>
      </div>
      <div style="margin-top:12px; display:flex; gap:20px; align-items:center; flex-wrap:wrap">
        <label class="m3-check"><input type="checkbox" name="auto_threshold" checked> Auto-calibrate relevance threshold (recommended)</label>
        <div>
          <label class="m3-fieldlabel">Manual threshold (if unchecked)</label>
          <input type="number" name="high_relevance_threshold" value="0.70" min="0.1" max="0.95" step="0.05" style="width:110px;" class="m3-input">
        </div>
      </div>
      <div style="margin-top:12px">
        <label class="m3-fieldlabel">spaCy model</label>
        <input type="text" name="spacy_model" value="en_core_web_sm" class="m3-input">
      </div>
      <div class="m3-field-grid" style="margin-top:12px">
        <div>
          <label class="m3-fieldlabel">Search intent</label>
          <select name="search_intent" class="m3-input">
            <option value="informational" selected>Informational</option>
            <option value="commercial">Commercial</option>
            <option value="navigational">Navigational</option>
            <option value="transactional">Transactional</option>
            <option value="comparison">Comparison</option>
            <option value="local">Local</option>
          </select>
        </div>
        <div>
          <label class="m3-fieldlabel">AI-engine matrix (comma-separated)</label>
          <input type="text" name="engine_matrix" value="Google AI Overviews, Google AI Mode, ChatGPT, Gemini, Claude, Perplexity, Bing Copilot, Grok, Meta AI, DeepSeek" class="m3-input">
        </div>
      </div>
      <div class="m3-field-grid" style="margin-top:12px">
        <div>
          <label class="m3-fieldlabel">7) Custom Entity Weighting / Ontology Mapping</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">One per line: <code class="m3-code">Entity|weight</code> (weight &gt; 0, default 1) then <code class="m3-code">Entity|alias1,alias2</code> for sub-brands / product / patent names.</div>
          <textarea name="entity_weighting" class="m3-input" placeholder="AcmeCorp|1.5&#10;GlobexInc|1.0&#10;AcmeCorp Pro|AcmeCorp"></textarea>
        </div>
        <div>
          <label class="m3-fieldlabel">6) Query Templates for Search Intent (format: intent|pattern)</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">One per line, <code class="m3-code">{topic}</code> / <code class="m3-code">{brand}</code> substituted, e.g. <code class="m3-code">transactional|best {topic} software</code>.</div>
          <textarea name="query_templates" class="m3-input" placeholder="transactional|best {topic} options&#10;comparison|{brand} vs alternatives"></textarea>
        </div>
      </div>
      <div class="m3-field-grid" style="margin-top:12px">
        <div>
          <label class="m3-fieldlabel">10) Search-Engine Scraping Footprints (SERP snippet types)</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">Specific source URLs surfaced by an AI engine, ingested separately. Format: <code class="m3-code">engine|label|url</code>.</div>
          <textarea name="serp_footprints" class="m3-input" placeholder="Google AI Overviews|industry survey|https://research.example.com/path&#10;Perplexity|guide|https://guide.example.com/path"></textarea>
        </div>
        <div>
          <label class="m3-fieldlabel">8) Historical Ground-Truth Corpora (internal brand docs)</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">PDF / whitepaper / Markdown file paths so the tool compares Internal Brand Perception Vector vs Web RAG Vector. One per line.</div>
          <textarea name="corpus_files" class="m3-input" placeholder="./corpus/whitepaper.pdf&#10;./corpus/product-specs.txt"></textarea>
        </div>
      </div>
      <div class="m3-field-grid" style="margin-top:12px">
        <div>
          <label class="m3-fieldlabel">11) Competitor Content Change Logs — RSS / sitemap feeds</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">Competitor / industry feeds ingested in near-real-time for freshness.</div>
          <textarea name="content_feeds" class="m3-input" placeholder="https://competitor.com/feed.xml&#10;https://competitor.com/sitemap.xml"></textarea>
        </div>
        <div>
          <label class="m3-fieldlabel">11b) Local corpus directory (ground-truth folder)</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">Alternative to per-file list — point at an entire internal docs folder.</div>
          <input type="text" name="corpus_dir" class="m3-input" placeholder="./corpus/ground-truth">
        </div>
      </div>
      <div class="m3-field-grid" style="margin-top:12px">
        <div>
          <label class="m3-fieldlabel">Synthetic query count</label>
          <input type="number" name="synthetic_query_count" value="12" min="0" max="100" class="m3-input">
        </div>
        <div>
          <label class="m3-fieldlabel">Chunk / density settings</label>
          <div style="display:flex;gap:8px">
            <input class="m3-input" type="number" name="chunk_tokens" value="512" min="64" max="8192" title="Chunk tokens" style="width:110px">
            <input class="m3-input" type="number" name="target_entity_density" value="0.015" step="0.001" min="0" max="1" title="Target entity density" style="width:110px">
            <input class="m3-input" type="number" name="top_k_retrieval" value="5" min="1" max="50" title="Top-k retrieval" style="width:90px">
          </div>
          <div class="hint" style="margin:4px 0 0;font-size:11px;">chunk tokens · target density · top-k</div>
        </div>
      </div>
      <div class="m3-field-grid" style="margin-top:12px">
        <div>
          <label class="m3-fieldlabel">9) Target Embedding Model Selection</label>
          <input type="text" name="embedding_model" value="sentence-transformers/all-MiniLM-L6-v2" class="m3-input">
          <div class="hint" style="margin:4px 0 0;font-size:11px;">Pick the embedding architecture matching the AI engine's vector space (e.g. <code class="m3-code">bge-large-en-v1.5</code>, <code class="m3-code">all-MiniLM-L6-v2</code>). Operator supplies a local model.</div>
        </div>
        <div>
          <label class="m3-fieldlabel">Ollama model (optional local LLM)</label>
          <input type="text" name="ollama_model" value="llama3" class="m3-input">
          <div class="hint" style="margin:4px 0 0;font-size:11px;">Ollama base URL:</div>
          <input type="text" name="ollama_base_url" placeholder="http://localhost:11434" class="m3-input">
        </div>
      </div>
    </div>
  </div>

  <div class="run-bar">
    <button type="submit" class="m3-btn" id="runBtn">Run Full Audit — 10 engines</button>
    <button type="button" class="m3-btn tonal" id="outputsBtn" style="display:none">Show Outputs</button>
    <span class="hint" id="status" style="margin:0"></span>
  </div>

  <div class="m3-progress-block" id="barwrap" style="display:none">
    <div class="m3-barlabel"><span id="stage">Initializing…</span><span><span id="pct">0%</span> · <span id="timer">00:00</span></span></div>
    <div class="m3-progress-track"><div class="m3-progress-fill" id="barfill"></div></div>
  </div>

  <div class="m3-console" id="console" style="display:none" aria-live="polite"></div>
</form>
</div>

<div id="page-features" class="page"></div>
<div id="page-outputs" class="page"></div>
<div id="result"></div>
<div id="toasts"></div>
<footer class="ent-footer">
  <span><b>RAG-EVDA Enterprise 2026</b> · Material 3 Expressive · 2026 Pixel type (Google Sans / Roboto Flex) · zero-cost local inference</span>
  <span>Dark / light is fully token-driven — every surface re-renders on toggle · <a href="/history">History</a> · <a href="/schedules">Schedules</a></span>
</footer>

<script>
// ---- enterprise theme toggle (fixed dark/light rendering) ----
const themeBtn = document.getElementById('themeBtn');
const metaTheme = document.getElementById('metaTheme');
function applyTheme(t, animate){
  if(animate){ document.body.classList.add('theme-anim'); setTimeout(()=>document.body.classList.remove('theme-anim'), 450); }
  const light = (t==='light');
  document.body.classList.toggle('light', light);
  document.body.setAttribute('data-theme', light ? 'light' : 'dark');
  document.documentElement.style.colorScheme = light ? 'light' : 'dark';
  if(metaTheme) metaTheme.setAttribute('content', light ? '#F3EDF7' : '#141218');
  themeBtn.textContent = light ? ' Light' : ' Dark';
}
let savedTheme = null;
try{ savedTheme = localStorage.getItem('ragevda-theme'); }catch(e){}
if(!savedTheme && window.matchMedia){ savedTheme = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'; }
applyTheme(savedTheme||'dark', false);
themeBtn.onclick = () => {
  const next = (document.body.classList.contains('light') || document.body.getAttribute('data-theme')==='light') ? 'dark':'light';
  try{ localStorage.setItem('ragevda-theme', next); }catch(e){}
  applyTheme(next, true); toast(next==='light' ? 'Light mode — Material 3 light tokens applied.' : 'Dark mode — Material 3 dark tokens applied.');
};
function toast(msg, kind){
  const box=document.getElementById('toasts'); if(!box) return;
  const el=document.createElement('div'); el.className='toast'+(kind==='ok'?' ok':kind==='bad'?' bad':''); el.innerHTML=msg;
  box.appendChild(el); setTimeout(()=>{ el.style.opacity='0'; setTimeout(()=>el.remove(),400); }, 4200);
}
// ---- fluid stepper navigation ----
let lastJob=null;
function goStep(which){
  const inputs=document.getElementById('page-inputs'), feats=document.getElementById('page-features'), outs=document.getElementById('page-outputs');
  inputs.classList.remove('active'); feats.classList.remove('active'); outs.classList.remove('active');
  setStep('step1',''); setStep('step2',''); setStep('step3','');
  if(which==='inputs'){ inputs.classList.add('active'); setStep('step1','active'); }
  else if(which==='features'){
    if(!lastJob){ toast('Run an audit first — analysis appears here.'); inputs.classList.add('active'); setStep('step1','active'); return; }
    feats.classList.add('active'); setStep('step1','done'); setStep('step2','active'); loadFeatures(lastJob, true);
  } else {
    if(!lastJob){ toast('Run an audit first — outputs appear here.'); inputs.classList.add('active'); setStep('step1','active'); return; }
    outs.classList.add('active'); setStep('step1','done'); setStep('step2','done'); setStep('step3','active'); loadOutputs(lastJob, true);
  }
  window.scrollTo({top:0, behavior:'smooth'});
}

const adv = document.getElementById('advToggle');
adv.onclick = () => {
  const p = document.getElementById('advPanel');
  const hidden = p.style.display === 'none';
  p.style.display = hidden ? 'block' : 'none';
  adv.textContent = (hidden ? '' : '') + ' Enterprise inputs 6–11 + engine tuning (auto-filled — review & expand)';
};

function splitList(s){ return s.split(/[\n,]/).map(x=>x.trim()).filter(Boolean); }

// ---- Auto-Detect: fetch the submitted URL/brand and fill ALL fields ----
const probeBtn=document.getElementById('probeBtn');
const probeStatus=document.getElementById('probeStatus');
function setProbeStatus(html, ok){
  probeStatus.innerHTML=html;
  probeStatus.style.display='block';
  probeStatus.style.color = ok ? 'var(--m3-tertiary)' : 'var(--m3-error)';
}
function fillField(name, value){
  const el=document.querySelector('[name="'+name+'"]');
  if(!el) return false;
  const type=(el.getAttribute('type')||'text').toLowerCase();
  const tag=el.tagName.toUpperCase();
  if(type==='checkbox'){
    if(value){ el.checked=true; }
  } else if(tag==='SELECT'){
    if([].slice.call(el.options).some(o=>o.value===String(value))){ el.value=String(value); }
  } else if(type==='number'){
    if(value!=null && value!==''){ el.value=String(value); }
  } else {
    el.value = value==null ? '' : String(value);
  }
  // open the advanced panel whenever an advanced-only field gets filled
  const core=['target_brand','industry_topics','competitor_entities','crawl_depth','locality'];
  if(core.indexOf(name)<0){
    const p=document.getElementById('advPanel');
    if(p && p.style.display==='none'){
      p.style.display='block';
      document.getElementById('advToggle').textContent=' Enterprise inputs 6–11 + engine tuning (auto-filled — review & expand)';
    }
  }
  el.dispatchEvent(new Event('change',{bubbles:true}));
  return true;
}
async function runProbe(){
  const input=document.querySelector('[name="target_brand"]').value.trim();
  if(!input){ setProbeStatus('Enter a brand or URL first.', false); return; }
  probeBtn.disabled=true; probeBtn.textContent='⏳ Deep-researching…';
  setProbeStatus(' <b>Stage 1/4</b> fetching live homepage + robots / sitemap / about / products…', true);
  const stages=document.getElementById('probeStages'); stages.style.display='block';
  stages.innerHTML='<div class="skel" style="height:14px; margin:4px 0"></div><div class="skel" style="height:14px; margin:4px 0"></div>';
  const stageTimer=setInterval(()=>{ stages.innerHTML+=''; }, 1000);
  try{
    const resp=await fetch('/api/probe',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({query:input})});
    const d=await resp.json();
    clearInterval(stageTimer); stages.style.display='none';
    if(d.error){ setProbeStatus('Detect failed: '+d.error, false); probeBtn.disabled=false; probeBtn.textContent='Auto-Detect Deep Research'; return; }
    // Fill EVERY returned field that has a matching form element.
    const known=['target_brand','industry_topics','competitor_entities','crawl_depth',
      'locality','harvester','prefer_searxng','searxng_base_url','auto_threshold',
      'high_relevance_threshold','search_intent','spacy_model','embedding_model',
      'engine_matrix','entity_weighting','ontology_aliases','query_templates',
      'serp_footprints','content_feeds','corpus_files','corpus_dir','chunk_tokens',
      'chunk_overlap_tokens','target_entity_density','top_k_retrieval',
      'synthetic_query_count','ollama_base_url','ollama_model'];
    let filled=[], skipped=[];
    for(const key of Object.keys(d)){
      if(key.indexOf('_')===0) continue;
      if(known.indexOf(key)<0) continue;
      if(fillField(key, d[key])) filled.push(key); else skipped.push(key);
    }
    const detested = {brand:d.target_brand,
      topics:(d.industry_topics||'').split('\n').filter(Boolean).length,
      comps:(d.competitor_entities||'').split('\n').filter(Boolean).length,
      locality:d.locality||'auto'};
    try{
      document.getElementById('hsTopics').textContent=detested.topics||'—';
      document.getElementById('hsComps').textContent=detested.comps||'—';
      document.getElementById('hsDepth').textContent=d.crawl_depth||'—';
      document.getElementById('hsLocality').textContent=detested.locality||'—';
    }catch(e){}
    const badge=document.getElementById('fb-brand'); if(badge) badge.classList.add('show');
    let note='';
    if(d._meta){ const m=d._meta; note=' — source: '+(m.title||m.domain||'web')+' · '+(m.note||''); }
    if(d._meta && d._meta.fields_filled){ note+=' · verified fields: '+d._meta.fields_filled.length; }
    const missing = ['corpus_dir','corpus_files'].filter(k=>{
      const el=document.querySelector('[name="'+k+'"]'); return el && (!el.value||!el.value.trim());
    });
    let msg=' <b>Deep research complete.</b> Brand "'+detested.brand+'" with '+detested.topics+' live topics &amp; '+
      detested.comps+' verified competitors (locality '+detested.locality+'). <b>'+filled.length+'/'+known.length+' enterprise fields auto-filled</b> from real-time evidence.'+note;
    if(missing.length) msg+=' · <b>Add manually:</b> '+missing.join(', ')+' (internal paths only — undetectable from the web)';
    setProbeStatus(msg, true);
    toast(' Deep research filled '+filled.length+' fields with verified live data.', 'ok');
  }catch(err){ setProbeStatus('Detect error: '+err, false); }
  probeBtn.disabled=false; probeBtn.textContent='Auto-Detect Deep Research';
}
probeBtn.addEventListener('click', runProbe);
document.querySelector('[name="target_brand"]').addEventListener('keydown',(e)=>{ if(e.key==='Enter'){ e.preventDefault(); runProbe(); } });

let pollTimer=null, startTs=0, tickTimer=null;
function fmt(sec){ const m=String(Math.floor(sec/60)).padStart(2,'0'); const s=String(sec%60).padStart(2,'0'); return m+':'+s; }

document.getElementById('auditForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target, fd = new FormData(form);
  const brand = fd.get('target_brand').trim();
  const topics = splitList(fd.get('industry_topics'));
  const comps = splitList(fd.get('competitor_entities'));
  if(!brand){ alert('Brand name required'); return; }
  if(!topics.length){ alert('At least one topic'); return; }
  if(!comps.length){ alert('At least one competitor'); return; }

  const btn=document.getElementById('runBtn');
  btn.disabled=true;
  const outBtn=document.getElementById('outputsBtn'); if(outBtn) outBtn.style.display='none';
  const consoleEl=document.getElementById('console');
  const statusEl=document.getElementById('status');
  const barwrap=document.getElementById('barwrap');
  consoleEl.style.display='block'; consoleEl.innerHTML='';
  barwrap.style.display='block';
  statusEl.textContent='Queued — starting full 10-engine live audit…';
  toast(' Full audit started — 10 micro-engines running locally.');
  startTs=Date.now();
  document.getElementById('barfill').style.width='4%';
  const pctEl=document.getElementById('pct'); if(pctEl) pctEl.textContent='4%';
  document.getElementById('stage').textContent='Initializing…';
  tickTimer=setInterval(()=>{ document.getElementById('timer').textContent=fmt(Math.floor((Date.now()-startTs)/1000)); },1000);

  const body=new URLSearchParams();
  for(const [k,v] of fd.entries()) body.append(k,v);
  let jobId=null;
  try {
    const resp=await fetch('/run',{method:'POST',body});
    const data=await resp.json();
    if(data.error){ statusEl.innerHTML='<span class="err">'+data.error+'</span>'; btn.disabled=false; return; }
    jobId=data.job;
    poll(jobId);
  } catch(err){ statusEl.innerHTML='<span class="err">Request failed: '+err+'</span>'; btn.disabled=false; }
});

function poll(jobId){
  lastJob=jobId;
  fetch('/status/'+jobId).then(r=>r.json()).then(d=>{
    const c=document.getElementById('console');
    if(d.logs){ c.innerHTML = d.logs.slice(-300).map(escLog).join('<br>'); }
    c.scrollTop=c.scrollHeight;
    if(typeof d.progress==='number'){ document.getElementById('barfill').style.width=Math.max(4,d.progress)+'%'; const p=document.getElementById('pct'); if(p) p.textContent=d.progress+'%'; }
    if(d.stage) document.getElementById('stage').textContent=d.stage;
    if(d.status==='done'){ finish(jobId); return; }
    if(d.status==='error'){ document.getElementById('status').innerHTML='<span class="err">Error: '+d.error+'</span>'; toast('Audit failed: '+d.error,'bad'); stopTimers(); document.getElementById('runBtn').disabled=false; return; }
    document.getElementById('status').textContent='Running 10-engine audit… ('+d.progress+'%)';
    pollTimer=setTimeout(()=>poll(jobId), 1000);
  }).catch(()=>{ pollTimer=setTimeout(()=>poll(jobId), 1500); });
}
function escLog(s){
  s=String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');
  if(/error|fail/i.test(s)) return '<span style="color:var(--m3-error)">'+s+'</span>';
  if(/complete|verified|complete\.|done/i.test(s)) return '<span style="color:var(--m3-tertiary)">'+s+'</span>';
  return s;
}

function stopTimers(){ if(pollTimer) clearTimeout(pollTimer); if(tickTimer) clearInterval(tickTimer); }

function finish(jobId){
  lastJob=jobId;
  stopTimers();
  document.getElementById('barfill').style.width='100%';
  const p=document.getElementById('pct'); if(p) p.textContent='100%';
  document.getElementById('stage').textContent='Complete — 10/10 engines';
  document.getElementById('status').textContent='Audit complete — deep analysis ready.';
  document.getElementById('runBtn').disabled=false;
  const outBtn=document.getElementById('outputsBtn'); if(outBtn){ outBtn.style.display=''; outBtn.onclick=()=>loadOutputs(jobId); }
  toast(' Audit complete — opening in-depth 10-engine analysis.', 'ok');
  document.getElementById('page-inputs').classList.remove('active');
  loadFeatures(jobId);
}

function setStep(id, state){
  const el=document.getElementById(id);
  if(!el) return;
  el.classList.remove('active','done');
  if(state) el.classList.add(state);
}

function loadFeatures(jobId, fromTab){
  lastJob=jobId;
  const el=document.getElementById('page-features');
  el.innerHTML='<div class="card"><div class="skel" style="height:22px"></div><div class="skel" style="height:14px;margin-top:10px"></div><div class="skel" style="height:14px;margin-top:10px"></div><p class="hint">Synthesizing 10-engine deep analysis — methodology, per-engine evidence, verification…</p></div>';
  setStep('step1','done'); setStep('step2','active'); setStep('step3','');
  if(!fromTab){ document.getElementById('page-inputs').classList.remove('active'); document.getElementById('page-outputs').classList.remove('active'); }
  el.classList.add('active');
  fetch('/page/analysis/'+jobId).then(r=>r.text()).then(h=>{
    el.innerHTML = h + '<div class="nav-btns"><button class="m3-btn" onclick="loadOutputs(\''+jobId+'\')">Show Outputs — verified report →</button><button class="m3-btn outlined" onclick="goStep(\'inputs\')">← Back to Inputs</button></div>';
    window.scrollTo({top:0, behavior:'smooth'});
  }).catch(()=>{ el.innerHTML='<div class="card err">Failed to load analysis.</div>'; });
}

function loadOutputs(jobId, fromTab){
  lastJob=jobId;
  const el=document.getElementById('page-outputs');
  el.innerHTML='<div class="card"><div class="skel" style="height:22px"></div><div class="skel" style="height:14px;margin-top:10px"></div><p class="hint">Compiling verified outputs — KPIs, proximity, citation gaps, off-page targets, downloads…</p></div>';
  setStep('step1','done'); setStep('step2','done'); setStep('step3','active');
  if(!fromTab){ document.getElementById('page-features').classList.remove('active'); }
  el.classList.add('active');
  fetch('/page/outputs/'+jobId).then(r=>r.text()).then(h=>{
    el.innerHTML = h + '<div class="nav-btns"><button class="m3-btn outlined" onclick="backToFeatures()">← Back to Analysis</button><button class="m3-btn tonal" onclick="goStep(\'inputs\')">＋ New Audit</button></div>';
    window.scrollTo({top:0, behavior:'smooth'});
    toast(' Outputs ready — verified competitive report below.', 'ok');
  }).catch(()=>{ el.innerHTML='<div class="card err">Failed to load outputs.</div>'; });
}

function backToFeatures(){
  setStep('step3','');
  document.getElementById('page-outputs').classList.remove('active');
  setStep('step2','active');
  document.getElementById('page-features').classList.add('active');
  window.scrollTo(0,0);
}
</script>
</div></body></html>
"""


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def _start_run(profile: dict) -> str:
    """Build a RunConfig from a profile dict and launch a background audit.

    Returns the new job id. Used by both the UI ('/run') and the scheduler, so
    scheduled runs land in the same ``web_output/jobs`` store and appear in
    History/Trends automatically.

    Concurrency: jobs queue persistently (SQLite) with a bounded worker pool
    runs ONE audit at a time. A second submission while one is running raises a
    friendly error instead of launching a parallel run whose logs/progress would
    cross-contaminate the first job's live view.
    """
    # Persistent queue: no single-flight rejection; concurrency is bounded
    # by the worker pool (RAGEVDA_WORKERS). Queue depth is unlimited.
    pass
    from .config import RunConfig

    brand = (profile.get("target_brand") or "").strip()
    topics = [t.strip() for t in (profile.get("industry_topics") or []) if t and t.strip()]
    comps = [c.strip() for c in (profile.get("competitor_entities") or []) if c and c.strip()]
    if not brand or not topics or not comps:
        raise ValueError("brand, industry_topics and competitor_entities are required")
    try:
        depth = int(profile.get("crawl_depth") or 50)
    except ValueError:
        depth = 50
    try:
        hrt = float(profile.get("high_relevance_threshold") or 0.70)
    except ValueError:
        hrt = 0.70

    def _int(v, default):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    def _float(v, default):
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    # "Entity|weight" or "Entity|alias1,alias2" — feeds both weights & ontology.
    ontology = {}
    entity_weights: Dict[str, float] = {}
    for line in (profile.get("entity_weighting") or profile.get("ontology_aliases") or "").splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        entity, value = line.split("|", 1)
        entity = entity.strip()
        value = value.strip()
        if not entity:
            continue
        try:
            w = float(value)
            if w > 0:
                entity_weights[entity] = w
            continue
        except ValueError:
            pass
        aliases = [a.strip() for a in value.split(",") if a.strip()]
        if aliases:
            ontology.setdefault(entity, [])
            ontology[entity].extend(a for a in aliases if a not in ontology[entity])

    feed_list = [f.strip() for f in (profile.get("content_feeds") or "").splitlines() if f.strip()]
    serp_footprints = [s.strip() for s in (profile.get("serp_footprints") or "").splitlines() if s.strip()]
    corpus_files = [c.strip() for c in (profile.get("corpus_files") or "").splitlines() if c.strip()]
    query_templates = {}
    for line in (profile.get("query_templates") or "").splitlines():
        if "|" not in line:
            continue
        intent, pattern = line.split("|", 1)
        intent, pattern = intent.strip(), pattern.strip()
        if intent and pattern:
            query_templates[intent] = pattern
    engine_list = [e.strip() for e in (profile.get("engine_matrix") or
                                       "Google AI Overviews, Google AI Mode, ChatGPT, Gemini, Claude, Perplexity, Bing Copilot, Grok, Meta AI, DeepSeek").split(",")
                   if e.strip()]

    cfg = RunConfig(
        target_brand=brand,
        industry_topics=topics,
        competitor_entities=comps,
        crawl_depth=depth,
        locality=profile.get("locality") or None,
        harvester=profile.get("harvester") or "duckduckgo",
        prefer_searxng=bool(profile.get("prefer_searxng")),
        searxng_base_url=profile.get("searxng_base_url") or None,
        corpus_dir=profile.get("corpus_dir") or None,
        corpus_files=corpus_files,
        embedding_model=profile.get("embedding_model") or "sentence-transformers/all-MiniLM-L6-v2",
        spacy_model=profile.get("spacy_model") or "en_core_web_sm",
        auto_threshold=bool(profile.get("auto_threshold", True)),
        high_relevance_threshold=hrt,
        search_intent=profile.get("search_intent") or "informational",
        query_templates=query_templates,
        ontology_aliases=ontology,
        entity_weighting=entity_weights,
        entity_domains={},
        content_feeds=feed_list,
        serp_footprints=serp_footprints,
        chunk_tokens=_int(profile.get("chunk_tokens"), 512),
        chunk_overlap_tokens=_int(profile.get("chunk_overlap_tokens"), 64),
        target_entity_density=_float(profile.get("target_entity_density"), 0.015),
        top_k_retrieval=_int(profile.get("top_k_retrieval"), 5),
        engine_matrix=engine_list,
        ollama_base_url=profile.get("ollama_base_url") or None,
        ollama_model=profile.get("ollama_model") or "llama3",
        use_llm=bool(profile.get("use_llm", True)),
        synthetic_query_count=_int(profile.get("synthetic_query_count"), 12),
        max_pages=_int(profile.get("max_pages"), 200),
        max_search_queries=_int(profile.get("max_search_queries"), 120),
        dedupe_near=bool(profile.get("dedupe_near", True)),
        require_real_models=bool(profile.get("require_real_models", True)),
        drift_history_keep=_int(profile.get("drift_history_keep"), 60),
        output_dir=os.path.join(WEB_OUTPUT, "jobs", "temp"),
    )
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    job_dir = os.path.join(WEB_OUTPUT, "jobs", job_id)
    os.makedirs(job_dir, exist_ok=True)
    cfg.output_dir = job_dir
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "queued", "logs": [], "progress": 2,
            "stage": "Queued", "dir": job_dir, "error": "",
        }
    if _USE_JOB_STORE:
        try:
            _jobs_store.create(job_id, job_dir)
        except Exception:
            pass
    _POOL.submit(_worker, job_id, cfg)
    return job_id


_PAGE_CSS = WEB_STYLE + """
/* ---- compact history / schedules pages (enterprise, theme-correct) ---- */
.wrap{max-width:1280px;margin:0 auto;padding:26px 24px 56px}
body{font-family:var(--m3-font)}
section{margin:32px 0}
h2{display:flex;align-items:center;gap:9px;font-family:var(--m3-font);font-size:19px;font-weight:700;
  color:var(--m3-on-surface);margin:0 0 14px;letter-spacing:-.2px}
h2::before{content:"";width:4px;height:19px;border-radius:var(--m3-shape-full);
  background:linear-gradient(180deg,var(--m3-primary),var(--m3-tertiary))}
table{width:100%;border-collapse:collapse;margin-top:6px;font-size:13px;background:var(--m3-surface-container-low);
  border:1px solid var(--m3-outline-variant);border-radius:var(--m3-shape-m);overflow:hidden;
  box-shadow:var(--m3-shadow-1)}
th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--m3-outline-variant);vertical-align:top}
th{color:var(--m3-on-surface-variant);text-transform:uppercase;font-size:10.5px;letter-spacing:.7px;
  background:var(--m3-surface-container);font-weight:700}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:color-mix(in srgb,var(--m3-primary) 8%,transparent)}
.row-good{background:color-mix(in srgb,var(--m3-tertiary) 14%,transparent) !important}
.row-bad{background:color-mix(in srgb,var(--m3-error) 15%,transparent) !important}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:16px;margin:16px 0 8px}
.kpi{background:var(--m3-surface-container-low);border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-m);padding:18px 20px;box-shadow:var(--m3-shadow-1)}
.kpi .v{font-family:var(--m3-font);font-size:28px;font-weight:800;color:var(--m3-on-surface)}
.kpi .l{color:var(--m3-on-surface-variant);font-size:11px;text-transform:uppercase;letter-spacing:.6px;margin-top:4px}
select,input,textarea{background:var(--m3-surface-container-high);color:var(--m3-on-surface);
  border:1px solid var(--m3-outline-variant);border-radius:var(--m3-shape-s);padding:10px 12px;font-size:13px;
  font-family:var(--m3-font);transition:.15s}
select:focus,input:focus,textarea:focus{outline:none;border-color:var(--m3-primary);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--m3-primary) 26%,transparent)}
textarea{width:100%;min-height:76px;resize:vertical}
.inline{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin:8px 0}
.inline label{color:var(--m3-on-surface-variant);font-size:12px;margin:0 0 4px}
button,input[type=submit]{background:var(--m3-primary);color:var(--m3-on-primary);border:none;padding:11px 20px;
  border-radius:var(--m3-shape-s);cursor:pointer;font-size:13px;font-weight:800;font-family:var(--m3-font);
  box-shadow:var(--m3-shadow-1);transition:.18s}
button:hover,input[type=submit]:hover{filter:brightness(1.06);transform:translateY(-1px)}
.muted{color:var(--m3-on-surface-variant)}
.footer{color:var(--m3-on-surface-variant);font-size:12.5px;margin-top:14px;line-height:1.7}
.card{background:var(--m3-surface-container-low);border:1px solid var(--m3-outline-variant);
  border-radius:var(--m3-shape-m);padding:20px 22px;margin-top:14px;box-shadow:var(--m3-shadow-1)}
code{background:var(--m3-surface-container-high);padding:1px 6px;border-radius:6px;font-size:12px}
.topnav{display:flex;gap:10px;margin-bottom:22px;flex-wrap:wrap}
.topnav a{background:var(--m3-surface-container-high);border:1px solid var(--m3-outline-variant);
  color:var(--m3-on-surface);padding:9px 16px;border-radius:var(--m3-shape-xs);font-size:13px;
  text-decoration:none;font-weight:700;transition:.16s}
.topnav a:hover{border-color:var(--m3-primary);color:var(--m3-primary);transform:translateY(-1px);
  box-shadow:var(--m3-shadow-1)}
/* ---- 2026 responsive hardening: bento -> single column <768px, lazy charts,
   paginated tables, system-font fallback, prefers-color-scheme ---- */
@media(max-width:768px){.bento{grid-template-columns:1fr}
  .bento .card{grid-column:span 12}.hero{padding:20px 16px}
  table{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}}
@media(prefers-color-scheme:light){:root{color-scheme:light}}
body{font-family:var(--m3-font,Google Sans,Roboto Flex,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif)}
img,canvas,iframe,svg{max-width:100%;height:auto}
img[loading],canvas[loading]{content-visibility:auto}
.m3-table-wrap{overflow-x:auto}
tr[data-page-hidden="1"]{display:none}
@media(max-width:720px){.kpis{grid-template-columns:1fr 1fr}.kpi .v{font-size:22px}}
"""


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — RAG-EVDA</title><style>{_PAGE_CSS}</style></head>
<body><div class="wrap">
<nav class="topnav"><a href="/"> Audit</a>
<a href="/history"> History &amp; Trends</a>
<a href="/schedules">⏱ Schedules</a></nav>
{body}</div></body></html>"""


def render_history_page(brand: str = None, old_id: str = None, new_id: str = None) -> str:
    runs = load_runs()
    if not runs:
        return _page("History & Trends",
            "<p class='muted'>No audit runs recorded yet. Run an audit first — "
            "every run is stored under <code>web_output/jobs</code> and appears "
            "here automatically.</p>")
    blist = brands(runs)
    if not brand or brand not in blist:
        brand = blist[0]
    br = runs_for_brand(runs, brand)
    latest = br[-1]
    chart = trend_chart(br, "both")
    rows = "".join(
        f"<tr><td>{r.generated_at.strftime('%Y-%m-%d %H:%M')}</td><td>{r.doc_count}</td>"
        f"<td>{r.composite_sov}%</td><td>{r.rag_invisibility_index}%</td>"
        f"<td><a href='/files/{r.job_id}/dashboard.html' target='_blank'>view</a></td></tr>"
        for r in br
    )
    diff_html = ""
    if old_id and new_id and old_id != new_id:
        old = next((x for x in br if x.job_id == old_id), None)
        new = next((x for x in br if x.job_id == new_id), None)
        if old and new:
            drows = ""
            for d in diff_runs(new, old):
                cls = "row-good" if d["improved"] else ("row-bad" if d["worsened"] else "")
                drows += (
                    f"<tr class='{cls}'><td>{d['topic']}</td>"
                    f"<td>{d['inv_old']}→{d['inv_new']} ({d['inv_delta']:+})</td>"
                    f"<td>{d['sov_old']}→{d['sov_new']} ({d['sov_delta']:+})</td>"
                    f"<td>{d['relevant_new']}</td></tr>"
                )
            diff_html = (
                f"<h2>Diff: {old.label} → {new.label}</h2>"
                "<table><thead><tr><th>Topic</th><th>Invisibility % (old→new)</th>"
                "<th>Share of Voice % (old→new)</th><th>Relevant docs (new)</th></tr></thead>"
                f"<tbody>{drows}</tbody></table>"
                "<div class='footer'>Green = improved (lower invisibility / higher SoV). "
                "Red = worsened. Deltas are computed from the real per-topic metrics of "
                "each run.</div>"
            )
    brand_opts = "".join(
        f"<option value='{b}' {'selected' if b == brand else ''}>{b}</option>" for b in blist)
    run_opts = "".join(
        f"<option value='{r.job_id}'>{r.generated_at.strftime('%m-%d %H:%M')} "
        f"(SoV {r.composite_sov}%)</option>" for r in br)
    body = f"""
    <form method="get" class="inline">
      <label>Brand:</label>
      <select name="brand" onchange="this.form.submit()">{brand_opts}</select>
    </form>
    <div class="kpis">
      <div class="kpi"><div class="v" style="color:var(--m3-tertiary)">{latest.composite_sov}%</div>
        <div class="l">Latest Vector SoV</div></div>
      <div class="kpi"><div class="v" style="color:var(--m3-error)">{latest.rag_invisibility_index}%</div>
        <div class="l">Latest Invisibility</div></div>
      <div class="kpi"><div class="v">{len(br)}</div><div class="l">Runs tracked</div></div>
      <div class="kpi"><div class="v">{latest.doc_count}</div><div class="l">Latest corpus docs</div></div>
    </div>
    <section><h2>Trend over time — {brand}</h2>{chart}
      <div class="footer">Each point is one real live audit. Re-run (or schedule) the
      same brand+topics to extend the timeline.</div></section>
    <section><h2>All runs for {brand}</h2>
      <table><thead><tr><th>When</th><th>Docs</th><th>SoV %</th>
      <th>Invisibility %</th><th>Report</th></tr></thead><tbody>{rows}</tbody></table></section>
    <section><h2>Compare two runs (per-topic diff)</h2>
      <form method="get" class="inline">
        <input type="hidden" name="brand" value="{brand}">
        <select name="old_id">{run_opts}</select>
        <span>→</span>
        <select name="new_id">{run_opts}</select>
        <button>Compare</button>
      </form>
      {diff_html}
    </section>
    """
    return _page("History & Trends", body)


def render_schedules_page() -> str:
    scheds = SCHEDULER.list()
    items = ""
    for s in scheds:
        nr = s.next_run()
        items += (
            f"<tr><td>{s.name}</td><td>{s.brand}</td><td>{s.interval_minutes} min</td>"
            f"<td>{'on' if s.enabled else 'off'}</td><td>{s.last_run or 'never'}</td>"
            f"<td>{nr.strftime('%Y-%m-%d %H:%M') if nr else '-'}</td>"
            f"<td><a href='/schedules?delete={s.id}'>delete</a></td></tr>"
        )
    if not items:
        items = "<tr><td colspan='7' class='muted'>No schedules yet.</td></tr>"
    body = f"""
    <section><h2>Active repeating audits</h2>
      <table><thead><tr><th>Name</th><th>Brand</th><th>Interval</th><th>State</th>
      <th>Last run</th><th>Next run</th><th></th></tr></thead><tbody>{items}</tbody></table>
      <div class="footer">The scheduler fires due profiles in the background (every 20s
      check). Each fire runs a full live audit and writes a normal report, so it shows
      up in <a href="/history" style="color:#7fb4ff">History &amp; Trends</a> automatically.</div>
    </section>
    <section><h2>New repeating audit</h2>
      <form method="post" action="/schedules" class="card">
        <div class="inline"><div><label>Name</label><br>
          <input name="name" placeholder="Weekly brand visibility check" style="min-width:200px"></div>
          <div><label>Target brand</label><br>
          <input name="target_brand" required style="min-width:200px"></div></div>
        <div><label>Industry topics (one per line or comma-separated)</label><br>
          <textarea name="industry_topics" required></textarea></div>
        <div><label>Competitors (one per line or comma-separated)</label><br>
          <textarea name="competitor_entities" required></textarea></div>
        <div class="inline">
          <div><label>Repeat every</label><br>
            <input type="number" name="interval_value" value="6" min="1" style="width:80px">
            <select name="interval_unit"><option value="min">minutes</option>
            <option value="hour" selected>hours</option>
            <option value="day">days</option></select></div>
          <div><label>Crawl depth</label><br>
            <input name="crawl_depth" value="50" style="width:80px"></div>
          <div><label>Locality</label><br>
            <input name="locality" value="US" style="width:80px"></div>
        </div>
        <div class="inline">
          <div><label>SearXNG base URL</label><br>
            <input name="searxng_base_url" placeholder="http://localhost:8080" style="min-width:200px"></div>
          <div><label>Local corpus dir</label><br>
            <input name="corpus_dir" placeholder="./corpus/ground-truth" style="min-width:180px"></div>
        </div>
        <div class="inline">
          <label style="display:flex;gap:6px;align-items:center;color:#c7d0e6">
            <input type="checkbox" name="prefer_searxng"> Prefer SearXNG (if URL set)</label>
          <label style="display:flex;gap:6px;align-items:center;color:#c7d0e6">
            <input type="checkbox" name="auto_threshold" checked> Auto-calibrate thresholds</label>
        </div>
        <button>Save schedule</button>
      </form>
    </section>
    """
    return _page("Schedules", body)


def create_app() -> Flask:
    import os as _os
    _tpl = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                       'web_templates')
    _st = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                      'static')
    app = Flask(__name__, template_folder=_tpl if _os.path.isdir(_tpl) else None,
                static_folder=_st if _os.path.isdir(_st) else None)
    try:
        from .security import rate_limited as _rl, check_api_key as _auth
    except Exception:
        _rl = None; _auth = None

    @app.route("/health")
    def health():
        """Lightweight liveness probe — 5 lines, zero model loads.

        Render / K8s hit this every 10s. Must never import torch,
        transformers, sentence-transformers, pandas or reportlab.
        """
        return Response(json.dumps({"ok": True, "service": "ragevda-lite"}),
                        mimetype="application/json")

    @app.route("/robots.txt")
    def robots():
        return Response("User-agent: *\nAllow: /\n",
                        mimetype="text/plain")

    @app.route("/")
    def index():
        import os as _os2
        _p = _os2.path.join(_os2.path.dirname(_os2.path.abspath(__file__)),
                          'web_templates', 'index.html')
        if _os2.path.exists(_p):
            with open(_p, encoding='utf-8') as _fh:
                return _fh.read().replace('__M3_STYLE__', WEB_STYLE)
        return INDEX_HTML.replace("__M3_STYLE__", WEB_STYLE)

    @app.route("/run", methods=["POST"])
    def run_audit():
        from flask import request as _rq
        try:
            from .security import rate_limited as _rl2, check_api_key as _auth2, \
                check_csrf as _csrf, api_key_configured as _akc
            ip = (_rq.remote_addr or 'local')
            if _rl2(ip):
                return Response(json.dumps({"error": "rate limited"}),
                                status=429, mimetype="application/json")
            if _akc():
                key = (_rq.headers.get('X-API-Key', '') or _rq.form.get('api_key', ''))
                if not _auth2(key):
                    return Response(json.dumps({"error": "unauthorized"}),
                                    status=401, mimetype="application/json")
                if not _csrf(_rq.cookies.get('csrf', ''), _rq.headers.get('X-CSRF-Token', '')):
                    return Response(json.dumps({"error": "csrf mismatch"}),
                                    status=403, mimetype="application/json")
        except Exception:
            pass
        form = request.form
        profile = {
            "target_brand": form.get("target_brand"),
            "industry_topics": [t.strip() for t in
                                form.get("industry_topics", "").replace("\n", ",").split(",") if t.strip()],
            "competitor_entities": [c.strip() for c in
                                    form.get("competitor_entities", "").replace("\n", ",").split(",") if c.strip()],
            "crawl_depth": _parse_int(form.get("crawl_depth"), 50),
            "locality": form.get("locality") or "",
            "harvester": form.get("harvester") or "duckduckgo",
            "prefer_searxng": _parse_bool(form.get("prefer_searxng"), False),
            "searxng_base_url": form.get("searxng_base_url") or "",
            "corpus_dir": form.get("corpus_dir") or "",
            "embedding_model": form.get("embedding_model") or "sentence-transformers/all-MiniLM-L6-v2",
            "spacy_model": form.get("spacy_model") or "en_core_web_sm",
            "auto_threshold": _parse_bool(form.get("auto_threshold"), True),
            "high_relevance_threshold": _parse_float(form.get("high_relevance_threshold"), 0.70),
            "search_intent": form.get("search_intent") or "informational",
            "engine_matrix": form.get("engine_matrix") or "",
            "ontology_aliases": form.get("ontology_aliases") or "",
            "entity_weighting": form.get("entity_weighting") or "",
            "query_templates": form.get("query_templates") or "",
            "corpus_files": form.get("corpus_files") or "",
            "serp_footprints": form.get("serp_footprints") or "",
            "content_feeds": form.get("content_feeds") or "",
            "chunk_tokens": _parse_int(form.get("chunk_tokens"), 512),
            "chunk_overlap_tokens": _parse_int(form.get("chunk_overlap_tokens"), 64),
            "target_entity_density": _parse_float(form.get("target_entity_density"), 0.015),
            "top_k_retrieval": _parse_int(form.get("top_k_retrieval"), 5),
            "synthetic_query_count": _parse_int(form.get("synthetic_query_count"), 12),
            "ollama_base_url": form.get("ollama_base_url") or "",
            "ollama_model": form.get("ollama_model") or "llama3",
        }
        try:
            job_id = _start_run(profile)
        except Exception as exc:
            return Response(json.dumps({"error": f"Config error: {exc}"}),
                            status=400, mimetype="application/json")
        return Response(json.dumps({"job": job_id}), mimetype="application/json")

    @app.route("/status/<job>")
    def status(job: str):
        with JOBS_LOCK:
            j = JOBS.get(job)
            snap = dict(j) if j else None
            logs = list(j["logs"]) if j else []
        if not snap and _USE_JOB_STORE:
            try:
                snap = _jobs_store.get(job)
                logs = (snap.get("logs", []) if snap else [])
            except Exception:
                pass
        if not snap:
            return Response(json.dumps({"status": "not_found"}), mimetype="application/json")
        return Response(json.dumps({
            "status": snap["status"],
            "progress": snap["progress"],
            "stage": snap["stage"],
            "logs": logs,
            "error": snap["error"],
        }), mimetype="application/json")

    @app.route("/api/probe", methods=["POST"])
    def api_probe():
        """Auto-detect brand / topics / competitors / locality from a URL or
        brand name entered in field 1. Returns a pre-fill dict keyed by form
        input names so the browser can populate every field.
        """
        data = request.get_json(silent=True) or {}
        query = (data.get("query") or data.get("target_brand") or "").strip()
        if not query:
            return Response(json.dumps({"error": "Enter a brand or URL first."}),
                            status=400, mimetype="application/json")
        try:
            from .analysis.auto_probe import probe

            result = probe(query)
        except Exception as exc:  # noqa: BLE001
            logger.exception("probe failed")
            return Response(json.dumps({"error": str(exc)}),
                            status=500, mimetype="application/json")
        if not result:
            return Response(json.dumps({"error": "Could not detect anything."}),
                            status=422, mimetype="application/json")
        return Response(json.dumps(result), mimetype="application/json")

    @app.route("/api/verify/<job>")
    def api_verify(job: str):
        """Return the full real-time verification breakdown for a finished audit.

        Exposes every sub-score (models, harvest, support, provenance, live),
        freshness grade, poisoning signals, and model identity so an operator
        can audit trust in the results programmatically (no black box).
        """
        data = _load_job_data(job)
        if data is None:
            return Response(json.dumps({"error": "job not found or not finished"}),
                            mimetype="application/json", status=404)
        meta = data.get("meta", {}) or {}
        di = meta.get("data_integrity", {}) or {}
        fs = di.get("freshness_summary", {}) or {}
        adv = data.get("advanced", {}) or {}
        pois = (adv.get("poisoning") or {})
        response = {
            "job_id": job,
            "verification_score": di.get("verification_score"),
            "verified": di.get("verified"),
            "sub_scores": {
                "models_real": di.get("models_real_score"),
                "harvest_ok": di.get("harvest_ok_score"),
                "support": di.get("support_score"),
                "provenance": di.get("provenance_score"),
                "live": di.get("live_score"),
            },
            "models": {
                "embedding_kind": di.get("embedding_kind"),
                "embedding_model": di.get("embedding_model"),
                "ner_kind": di.get("ner_kind"),
                "ner_model": di.get("ner_model"),
                "sentiment_model": di.get("sentiment_model"),
                "models_real": di.get("models_real"),
            },
            "harvest": {
                "harvest_ok": di.get("harvest_ok"),
                "harvested_docs": di.get("harvested_docs"),
                "dedup_removed": di.get("dedup_removed"),
                "entities_with_mentions": di.get("entities_with_mentions"),
                "entities_total": di.get("entities_total"),
                "support_fraction": di.get("support_fraction"),
                "provenance_complete": di.get("provenance_complete"),
            },
            "freshness": {
                "grade": fs.get("freshness_grade"),
                "composite": fs.get("freshness_composite"),
                "live_pct": fs.get("live_pct"),
                "fresh_pct": fs.get("fresh_pct"),
                "stale_pct": fs.get("stale_pct"),
                "median_age_days": fs.get("median_age_days"),
                "p90_age_days": fs.get("p90_age_days"),
                "p95_age_days": fs.get("p95_age_days"),
                "validated_at": fs.get("validated_at"),
            },
            "poisoning": {
                "brand_status": pois.get("brand_poisoning_status"),
                "brand_machine_score": pois.get("brand_machine_score"),
                "brand_repetition_score": pois.get("brand_repetition_score"),
                "brand_generated_phrase_hits": pois.get("brand_generated_phrase_hits"),
                "toxic_source_count": pois.get("toxic_source_count"),
                "total_sources": pois.get("total_sources"),
            },
        }
        return Response(json.dumps(response, indent=2), mimetype="application/json")

    @app.route("/files/<job>/<path:filename>")
    def files(job: str, filename: str):
        job_dir = os.path.join(WEB_OUTPUT, "jobs", job)
        # Lazily build the enterprise PDF on first request, then serve it.
        # A cached PDF older than the generator module itself is stale by
        # definition, so it is rebuilt automatically — code updates can never
        # leave users downloading yesterday's layout.
        if filename == "report.pdf":
            pdf_path = os.path.join(job_dir, "report.pdf")
            try:
                gen_mtime = os.path.getmtime(os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "reporting", "pdf_report.py"))
            except OSError:
                gen_mtime = 0
            stale = (not os.path.exists(pdf_path) or
                     os.path.getmtime(pdf_path) < gen_mtime)
            if stale:
                data = _load_job_data(job)
                if data is not None:
                    try:
                        from .reporting.pdf_report import render_report_pdf
                        render_report_pdf(data, job, pdf_path)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("PDF generation failed")
                        return Response(f"PDF generation failed: {exc}", status=500)
        return send_from_directory(job_dir, filename)

    @app.route("/page/features/<job>")
    def page_features(job: str):
        data = _load_job_data(job)
        if data is None:
            return Response("<p class='muted'>Job not found.</p>", mimetype="text/html")
        return Response(_lazy_narrative().features_html(data, job), mimetype="text/html")

    @app.route("/page/analysis/<job>")
    def page_analysis(job: str):
        """Full single-page Step-2 analysis: methodology + all 10 engines,
        rendered together with no further clicks."""
        data = _load_job_data(job)
        if data is None:
            return Response("<p class='muted'>Job not found.</p>", mimetype="text/html")
        body = _lazy_deep().render_all(job, data)
        return Response(body, mimetype="text/html")

    @app.route("/page/deep/<job>/<feature>")
    def page_deep(job: str, feature: str):
        data = _load_job_data(job)
        if data is None:
            return Response("<p class='muted'>Job not found.</p>", mimetype="text/html")
        body = _lazy_deep().render_deep(job, feature, data)
        return Response(
            "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Deep Analysis — RAG-EVDA</title><style>{_PAGE_CSS}</style>"
            "</head><body><div class='wrap'>"
            "<nav class='topnav'><a href='/'> Audit</a>"
            "<a href='/history'> History &amp; Trends</a>"
            "<a href='/schedules'>⏱ Schedules</a></nav>"
            + body +
            "<div style='margin-top:24px;text-align:center'>"
            f"<a href='/page/features/{job}' style='color:var(--m3-primary);font-weight:700'>← Back to Features Summary</a>"
            "</div>"
            "</div></body></html>",
            mimetype="text/html",
        )

    @app.route("/page/outputs/<job>")
    def page_outputs(job: str):
        data = _load_job_data(job)
        if data is None:
            return Response("<p class='muted'>Job not found.</p>", mimetype="text/html")
        return Response(_lazy_narrative().outputs_html(data, job), mimetype="text/html")

    @app.route("/history")
    def history():
        brand = request.args.get("brand")
        old_id = request.args.get("old_id")
        new_id = request.args.get("new_id")
        return Response(render_history_page(brand, old_id, new_id),
                        mimetype="text/html")

    @app.route("/schedules", methods=["GET", "POST"])
    def schedules():
        if request.method == "POST":
            form = request.form
            topics = [t.strip() for t in
                      form.get("industry_topics", "").replace("\n", ",").split(",") if t.strip()]
            comps = [c.strip() for c in
                     form.get("competitor_entities", "").replace("\n", ",").split(",") if c.strip()]
            try:
                interval = int(form.get("interval_value") or 360)
            except ValueError:
                interval = 360
            unit = form.get("interval_unit") or "min"
            interval *= {"min": 1, "hour": 60, "day": 1440}.get(unit, 1)
            sid = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]
            sched = Schedule(
                id=sid,
                name=form.get("name") or form.get("target_brand") or "schedule",
                brand=form.get("target_brand", "").strip(),
                topics=topics,
                competitors=comps,
                interval_minutes=interval,
                depth=int(form.get("crawl_depth") or 50),
                locality=form.get("locality") or None,
                harvester=form.get("harvester") or "duckduckgo",
                prefer_searxng=_parse_bool(form.get("prefer_searxng"), False),
                searxng_base_url=form.get("searxng_base_url") or None,
                search_intent=form.get("search_intent") or "informational",
                chunk_tokens=int(form.get("chunk_tokens") or 512),
                chunk_overlap_tokens=int(form.get("chunk_overlap_tokens") or 64),
                engine_matrix=[e.strip() for e in (form.get("engine_matrix") or
                    "Google AI Overviews, SearchGPT, Gemini, Perplexity, Bing Copilot").split(",") if e.strip()],
                corpus_dir=form.get("corpus_dir") or None,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                spacy_model="en_core_web_sm",
                auto_threshold=_parse_bool(form.get("auto_threshold"), True),
                high_relevance_threshold=0.70,
            )
            SCHEDULER.add(sched)
            return redirect("/schedules")
        delete = request.args.get("delete")
        if delete:
            SCHEDULER.remove(delete)
            return redirect("/schedules")
        return Response(render_schedules_page(), mimetype="text/html")

    # Start the background scheduler (fires due repeating audits).
    SCHEDULER.start(_start_run)

    return app


def _worker(job_id: str, cfg) -> None:
    with JOBS_LOCK:
        j = JOBS[job_id]
    handler = _JobLogHandler(job_id)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    rag_logger = logging.getLogger("ragevda")
    # get_logger() sets propagate=False on child loggers; re-enable it across
    # the ragevda namespace so all pipeline logs reach our capture handler.
    for name in list(logging.Logger.manager.loggerDict):
        if name == "ragevda" or name.startswith("ragevda."):
            logging.getLogger(name).propagate = True
    rag_logger.addHandler(handler)
    rag_logger.setLevel(logging.INFO)
    try:
        from .orchestrator import run

        # Pipeline modules (and their loggers) are imported above; they were
        # created with propagate=False by utils.get_logger. Re-enable
        # propagation across the ragevda namespace so all logs reach our
        # capture handler.
        for name in list(logging.Logger.manager.loggerDict):
            if name == "ragevda" or name.startswith("ragevda."):
                logging.getLogger(name).propagate = True

        run(cfg)
        with JOBS_LOCK:
            j["logs"].append("Audit complete.")
            j["progress"] = 100
            j["stage"] = "Complete"
            j["status"] = "done"
    except Exception as exc:  # noqa: BLE001
        logger.exception("audit failed")
        with JOBS_LOCK:
            j["logs"].append("ERROR: " + str(exc))
            j["error"] = str(exc)
            j["status"] = "error"
    finally:
        rag_logger.removeHandler(handler)


def run_app(host: str = "127.0.0.1", port: int = 8765) -> None:
    app = create_app()
    app.run(host=host, port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    run_app()
