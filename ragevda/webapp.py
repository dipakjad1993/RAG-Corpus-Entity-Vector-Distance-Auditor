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
from datetime import datetime
from typing import Dict, List

from flask import Flask, Response, request, send_from_directory, redirect

from .tracking import (load_runs, brands, runs_for_brand, diff_runs,
                        trend_chart, per_topic_trend_chart)
from .scheduler import Scheduler, Schedule
from .reporting import narrative as _narrative

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
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_OUTPUT = os.path.join(ROOT, "web_output")
SCHEDULER = Scheduler()

# Order matters: first matching keyword wins.
_PROGRESS_RULES = [
    ("audit complete", 100, "Complete"),
    ("wrote HTML dashboard", 98, "Generating dashboard"),
    ("wrote CSV", 96, "Generating CSV reports"),
    ("wrote JSON report", 94, "Generating JSON report"),
    ("context built", 85, "Building graphs & metrics"),
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
    low = msg.lower()
    prog = job.get("progress", 0)
    stage = job.get("stage", "")
    for keyword, value, label in _PROGRESS_RULES:
        if keyword in low:
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
            if value is not None:
                job["progress"] = max(prog, value)
                job["stage"] = label
                return
    # unknown lines keep current progress


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
<title>RAG-EVDA — RAG Corpus Entity & Vector Distance Auditor</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@600;700;800&display=swap');
:root{
  --bg:#0b0e14; --bg2:#0e1320; --surface:#141a28; --surface2:#1b2233; --border:#28324c;
  --text:#e8ecf4; --muted:#94a3c4; --accent:#6d8bff; --accent2:#34d399; --accent3:#a78bfa;
  --good:#34d399; --warn:#fbbf24; --bad:#fb7185; --radius:16px;
  --shadow:0 12px 34px rgba(0,0,0,.45); --shadow-sm:0 4px 16px rgba(0,0,0,.30);
  --ring:0 0 0 4px rgba(109,139,255,.22);
  --font:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --display:'Sora',var(--font);
}
* { box-sizing:border-box; }
html,body{ height:100%; }
body{
  margin:0; color:var(--text); font-family:var(--font); font-size:14px; line-height:1.65;
  -webkit-font-smoothing:antialiased; letter-spacing:.1px;
  background:
    radial-gradient(1200px 620px at 10% -12%, rgba(109,139,255,.14), transparent 60%),
    radial-gradient(1000px 520px at 102% -4%, rgba(52,211,153,.10), transparent 55%),
    var(--bg);
}
.wrap{ max-width:1080px; margin:0 auto; padding:28px 22px 60px; }
.brand{ display:flex; gap:15px; align-items:flex-start; }
.logo{ width:48px; height:48px; border-radius:14px; flex:0 0 auto;
  background:linear-gradient(135deg,var(--accent),var(--accent2)); color:#06121f;
  font-family:var(--display); font-weight:800; font-size:18px; letter-spacing:-.5px;
  display:flex; align-items:center; justify-content:center;
  box-shadow:0 10px 24px rgba(52,211,153,.35); }
.topbar{ display:flex; justify-content:space-between; align-items:flex-start; gap:16px;
  flex-wrap:wrap; padding:8px 0 20px; border-bottom:1px solid var(--border); }
header h1{ margin:0; font-family:var(--display); font-size:25px; font-weight:800; letter-spacing:-.4px;
  background:linear-gradient(92deg,#cfe0ff,var(--accent) 42%,var(--accent2));
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
header p{ color:var(--muted); margin:10px 0 0; font-size:13.5px; max-width:760px; line-height:1.7; }
.theme-btn{ background:rgba(255,255,255,.04); border:1px solid var(--border); color:var(--text);
  border-radius:12px; padding:9px 14px; cursor:pointer; font-size:13px; backdrop-filter:blur(6px);
  transition:.18s; }
.theme-btn:hover{ border-color:var(--accent); transform:translateY(-1px); }
.topnav{ display:flex; gap:10px; margin:18px 0 22px; flex-wrap:wrap; }
.topnav a{ background:rgba(255,255,255,.03); border:1px solid var(--border); color:var(--text);
  padding:9px 16px; border-radius:12px; font-size:13px; text-decoration:none; font-weight:600;
  transition:.18s; }
.topnav a:hover{ border-color:var(--accent); color:#fff; transform:translateY(-1px); box-shadow:var(--shadow-sm); }
form{ margin-top:6px; }
.card{ background:linear-gradient(180deg,var(--surface),var(--bg2)); border:1px solid var(--border);
  border-radius:var(--radius); padding:18px 20px; margin-bottom:16px; box-shadow:var(--shadow-sm);
  transition:.18s; }
.card:hover{ border-color:rgba(109,139,255,.45); }
.card label{ display:block; font-weight:700; font-size:13px; margin-bottom:7px; color:#dfe6f5; letter-spacing:.2px; }
.card .hint{ color:var(--muted); font-size:12.5px; margin:-2px 0 12px; line-height:1.6; }
input[type=text],input[type=number],textarea,select{ width:100%; background:var(--bg); color:var(--text);
  border:1px solid var(--border); border-radius:12px; padding:11px 13px; font-size:14px;
  font-family:inherit; transition:border-color .15s,box-shadow .15s; }
input[type=text]:focus,input[type=number]:focus,textarea:focus,select:focus{ outline:none;
  border-color:var(--accent); box-shadow:var(--ring); }
textarea{ min-height:88px; resize:vertical; line-height:1.55; }
.row{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; }
.row>div{ background:linear-gradient(180deg,var(--surface),var(--bg2)); border:1px solid var(--border);
  border-radius:var(--radius); padding:16px 18px; box-shadow:var(--shadow-sm); }
.row label{ display:block; font-weight:700; font-size:12px; margin-bottom:7px; color:#dfe6f5; }
.adv-link,.adv{ background:none; border:none; color:var(--accent); cursor:pointer; font-size:13px;
  padding:0; margin:6px 0 10px; font-weight:700; }
.adv-panel{ margin-top:6px; }
input[type=checkbox]{ width:auto; accent-color:var(--accent); }
button[type=submit],.run-btn{ background:linear-gradient(92deg,var(--accent),var(--accent2));
  color:#06121f; border:none; padding:13px 26px; border-radius:13px; font-size:15px; font-weight:800;
  cursor:pointer; box-shadow:0 8px 22px rgba(52,211,153,.28); transition:.18s; letter-spacing:.2px; }
button[type=submit]:hover,.run-btn:hover{ transform:translateY(-2px); filter:brightness(1.05);
  box-shadow:0 12px 28px rgba(52,211,153,.38); }
.howto{ background:linear-gradient(180deg,var(--surface),var(--bg2)); border:1px solid var(--border);
  border-radius:var(--radius); padding:14px 20px; margin-bottom:18px; box-shadow:var(--shadow-sm); }
.howto summary{ cursor:pointer; color:var(--accent); font-weight:700; font-size:14.5px; }
.howto-body{ margin-top:12px; font-size:13px; color:#c9d3ea; line-height:1.7; }
.howto-body p{ margin:8px 0; }
.howto-body b{ color:#eef2fb; }
#console{ background:#070a10; border:1px solid var(--border); border-radius:14px; padding:14px 16px;
  height:240px; overflow:auto; font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  font-size:12px; color:#8fd0ff; white-space:pre-wrap; line-height:1.55;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.02); }
.barwrap{ margin:14px 0 4px; }
.barlabel{ display:flex; justify-content:space-between; font-size:12.5px; color:var(--muted);
  margin-bottom:8px; font-weight:600; letter-spacing:.3px; }
.bar{ background:var(--bg); border:1px solid var(--border); border-radius:99px; height:12px; overflow:hidden; }
.barfill{ height:12px; width:0%; border-radius:99px;
  background:linear-gradient(90deg,var(--accent),var(--accent2)); transition:width .45s ease;
  box-shadow:0 0 14px rgba(52,211,153,.5); }
#status{ color:var(--muted); font-size:13px; margin-top:10px; }
.err{ color:var(--bad); }
#result{ margin-top:20px; }
#result h2{ font-family:var(--display); border-left:4px solid var(--accent); padding-left:12px;
  margin:0 0 12px; font-size:18px; }
iframe{ width:100%; height:82vh; border:1px solid var(--border); border-radius:14px; background:#fff;
  box-shadow:var(--shadow); }
.links a{ color:var(--accent); margin-right:16px; font-size:13px; text-decoration:none; font-weight:600; }
.links a:hover{ text-decoration:underline; }
.stepper{ display:flex; gap:0; align-items:center; margin:6px 0 22px; flex-wrap:wrap; }
.step{ display:flex; align-items:center; gap:10px; padding:10px 16px; border-radius:12px;
  background:rgba(255,255,255,.03); border:1px solid var(--border); color:var(--muted);
  font-weight:600; font-size:13px; }
.step .num{ width:24px; height:24px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; background:var(--surface2); border:1px solid var(--border);
  font-size:12px; font-weight:800; color:var(--muted); }
.step.active{ border-color:var(--accent); color:var(--text); box-shadow:var(--ring); }
.step.active .num{ background:linear-gradient(135deg,var(--accent),var(--accent2)); color:#06121f; border-color:transparent; }
.step.done .num{ background:var(--accent2); color:#06121f; border-color:transparent; }
.step-sep{ flex:1 1 24px; height:1px; background:var(--border); margin:0 8px; min-width:24px; }
.page{ display:none; }
.page.active{ display:block; }
.lead{ color:#c9d3ea; font-size:14px; line-height:1.7; margin:6px 0 14px; }
.narrative h2,.outputs h2{ font-family:var(--display); font-size:18px; font-weight:700; color:var(--text);
  margin:30px 0 12px; display:flex; align-items:center; gap:9px; }
.narrative h2::before,.outputs h2::before{ content:""; width:4px; height:18px; border-radius:3px;
  background:linear-gradient(180deg,var(--accent),var(--accent2)); }
.feat-list{ display:grid; gap:14px; margin:14px 0; }
.feat{ display:grid; grid-template-columns:54px 1fr; gap:16px; background:linear-gradient(180deg,var(--surface),var(--bg2));
  border:1px solid var(--border); border-radius:var(--radius); padding:18px 20px; box-shadow:var(--shadow-sm); }
.feat-num{ width:54px; height:54px; border-radius:14px; background:linear-gradient(135deg,var(--accent),var(--accent2));
  color:#06121f; font-family:var(--display); font-weight:800; font-size:22px; display:flex; align-items:center;
  justify-content:center; box-shadow:0 8px 18px rgba(52,211,153,.30); }
.feat-body h3{ margin:0 0 6px; font-family:var(--display); font-size:15.5px; color:var(--text); }
.feat-body p{ margin:0 0 8px; color:#c9d3ea; font-size:13px; line-height:1.65; }
.feat-body ul{ margin:0 0 10px; padding-left:18px; color:#c9d3ea; font-size:13px; line-height:1.6; }
.feat-metrics{ display:flex; gap:8px; flex-wrap:wrap; margin-top:6px; }
.chip{ background:var(--bg); border:1px solid var(--border); border-radius:99px; padding:5px 12px; font-size:12px; color:var(--muted); }
.chip b{ color:var(--text); font-weight:800; margin-right:4px; }
table.kv{ width:100%; border-collapse:separate; border-spacing:0; background:var(--surface);
  border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; font-size:13px; }
table.kv td{ padding:10px 14px; border-bottom:1px solid var(--border); vertical-align:top; }
table.kv tr:last-child td{ border-bottom:none; }
table.kv td:first-child{ color:var(--muted); width:46%; background:var(--surface2); font-weight:600; }
.verify-card{ border-radius:var(--radius); border:1px solid var(--border); padding:16px 18px; margin:12px 0; }
.verify-card.ok{ background:rgba(52,211,153,.08); border-color:var(--accent2); }
.verify-card.partial{ background:rgba(251,191,36,.08); border-color:var(--warn); }
.verify-head{ display:flex; align-items:center; gap:12px; margin-bottom:12px; font-weight:700; }
.verify-badge{ background:linear-gradient(92deg,var(--accent),var(--accent2)); color:#06121f; border-radius:8px;
  padding:4px 12px; font-size:12px; font-weight:800; }
.verify-card.partial .verify-badge{ background:linear-gradient(92deg,var(--warn),#fb923c); }
.verify-note{ color:var(--muted); font-size:12px; line-height:1.6; margin:10px 0 0; }
.dl-row{ display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
.dl{ background:linear-gradient(92deg,var(--accent),var(--accent2)); color:#06121f; text-decoration:none;
  font-weight:800; padding:10px 16px; border-radius:12px; font-size:13px; box-shadow:0 8px 22px rgba(52,211,153,.26); transition:.18s; }
.dl:hover{ transform:translateY(-1px); filter:brightness(1.05); }
.nav-btns{ display:flex; gap:12px; margin-top:18px; }
.btn-ghost{ background:rgba(255,255,255,.04); border:1px solid var(--border); color:var(--text); padding:11px 20px;
  border-radius:12px; font-weight:700; cursor:pointer; font-size:14px; transition:.18s; }
.btn-ghost:hover{ border-color:var(--accent); }
/* Light theme */
body.light{ --bg:#f5f8fc; --bg2:#ffffff; --surface:#ffffff; --surface2:#eef2f8; --border:#dde4ef;
  --text:#0f172a; --muted:#5b6b86; --shadow:0 12px 34px rgba(20,40,80,.10);
  --shadow-sm:0 4px 16px rgba(20,40,80,.08); --ring:0 0 0 4px rgba(109,139,255,.20); }
body.light header h1{ background:linear-gradient(92deg,#1e3a8a,var(--accent) 46%,#0f766e);
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
body.light .card,body.light .row>div{ box-shadow:var(--shadow-sm); }
body.light #console{ color:#9fd0ff; }
body.light .lead,body.light .feat-body p,body.light .narrative p,body.light .outputs p,body.light .feat-body li,
body.light .verify-note{ color:#334155; }
body.light .chip{ color:#5b6b86; }
body.light .feat{ background:linear-gradient(180deg,#ffffff,#f5f8fc); }
body.light table.kv td:first-child{ background:#eef2f8; }
</style></head>
<body><div class="wrap">
<nav class="topnav"><a href="/">🏠 Audit</a><a href="/history">📈 History &amp; Trends</a><a href="/schedules">⏱ Schedules</a></nav>
<div class="topbar"><div class="brand">
  <div class="logo">EV</div>
  <header>
    <h1>RAG Corpus Entity &amp; Vector Distance Auditor</h1>
    <p>Local, zero-cost vector intelligence. Fill the five inputs, run the audit,
       and get real proximity scores, the RAG Invisibility Index, off-page targets
       and prioritized recommendations. No OpenAI / Ahrefs / Semrush keys.</p>
  </header>
</div>
<button class="theme-btn" id="themeBtn">🌙 Dark</button></div>

<div class="stepper">
  <div class="step active" id="step1"><span class="num">1</span> Inputs</div>
  <div class="step-sep"></div>
  <div class="step" id="step2"><span class="num">2</span> Analysis</div>
  <div class="step-sep"></div>
  <div class="step" id="step3"><span class="num">3</span> Outputs</div>
</div>

<div id="page-inputs" class="page active">
<form id="auditForm">
  <div class="card">
    <label>1) Target Brand Name</label>
    <div class="hint">The precise name of your brand or site (e.g. "Acme Software").</div>
    <input type="text" name="target_brand" placeholder="Acme Software" required>
  </div>

    <div class="card">
      <label>2) Target Industry Topics / Concepts</label>
      <div class="hint">Any number of high-value contextual topics or seed keywords — no limit. One per line or comma-separated.</div>
      <textarea name="industry_topics" placeholder="enterprise churn prediction&#10;SaaS pipeline analytics&#10;CRM automation" required></textarea>
    </div>

    <div class="card">
      <label>3) Competitor Entities</label>
      <div class="hint">Any number of direct competitor brand names — no limit. One per line or comma-separated.</div>
      <textarea name="competitor_entities" placeholder="Salesforce&#10;HubSpot&#10;Zendesk" required></textarea>
    </div>

  <div class="row">
    <div class="card">
      <label>4) Crawl Depth</label>
      <div class="hint">Pages / results to scrape per query (e.g. 50 or 100).</div>
      <input type="number" name="crawl_depth" value="50" min="1" max="200">
    </div>
    <div class="card">
      <label>5) Locality (optional)</label>
      <div class="hint">Region / country code for local SEO (e.g. US, UK, Detroit). Leave blank for global.</div>
      <input type="text" name="locality" placeholder="US">
    </div>
  </div>

  <div class="card">
    <div class="adv" id="advToggle">▸ Advanced options (harvester, models)</div>
    <div id="advPanel" style="display:none; margin-top:14px;">
      <div class="row">
        <div>
          <label>Harvester</label>
          <select name="harvester">
            <option value="duckduckgo" selected>DuckDuckGo (live, free)</option>
            <option value="searxng">SearXNG (self-hosted)</option>
            <option value="file">Local corpus folder</option>
          </select>
          <label style="display:flex;align-items:center;gap:6px;margin-top:8px;font-size:12px;color:#9aa6c4">
            <input type="checkbox" name="prefer_searxng"> Prefer SearXNG (use my SearXNG URL as the primary live search when set)
          </label>
        </div>
      </div>
      <div class="row" style="margin-top:12px;">
        <div>
          <label>SearXNG base URL</label>
          <input type="text" name="searxng_base_url" placeholder="http://localhost:8080">
        </div>
      </div>
      <div style="margin-top:12px; display:flex; gap:18px; align-items:center;">
        <label style="margin:0;"><input type="checkbox" name="auto_threshold" checked> Auto-calibrate relevance threshold (recommended)</label>
        <div>
          <label>Manual threshold (if unchecked)</label>
          <input type="number" name="high_relevance_threshold" value="0.70" min="0.1" max="0.95" step="0.05" style="width:100px; display:inline-block;">
        </div>
      </div>
      <div style="margin-top:12px;">
        <label>spaCy model</label>
        <input type="text" name="spacy_model" value="en_core_web_sm">
      </div>
      <div class="row" style="margin-top:12px;">
        <div>
          <label>Search intent</label>
          <select name="search_intent">
            <option value="informational" selected>Informational</option>
            <option value="commercial">Commercial</option>
            <option value="navigational">Navigational</option>
            <option value="transactional">Transactional</option>
            <option value="comparison">Comparison</option>
            <option value="local">Local</option>
          </select>
        </div>
        <div>
          <label>AI-engine matrix (comma-separated)</label>
          <input type="text" name="engine_matrix" value="Google AI Overviews, SearchGPT, Gemini, Perplexity, Bing Copilot">
        </div>
      </div>
      <div class="row" style="margin-top:12px;">
        <div>
          <label>7) Custom Entity Weighting / Ontology Mapping</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">
            One per line: <code>Entity|weight</code> (weight &gt; 0, default 1) to
            prioritise an entity in retrieval scoring, then
            <code>Entity|alias1,alias2</code> for sub-brands / product / patent names.</div>
          <textarea name="entity_weighting" placeholder="Acme Software|1.5&#10;Salesforce|1.0&#10;Acme Cloud|Acme Software"></textarea>
        </div>
        <div>
          <label>6) Query Templates for Search Intent (format: intent|pattern)</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">
            One per line, <code>{topic}</code> / <code>{brand}</code> are substituted,
            e.g. <code>transactional|best {topic} software</code>.</div>
          <textarea name="query_templates" placeholder="transactional|best {topic} software&#10;comparison|{brand} vs {competitor}"></textarea>
        </div>
      </div>
      <div class="row" style="margin-top:12px;">
        <div>
          <label>10) Search-Engine Scraping Footprints (SERP snippet types)</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">
            Specific source URLs surfaced by an AI engine, ingested separately.
            Format: <code>engine|label|url</code>.</div>
          <textarea name="serp_footprints" placeholder="Google AI Overviews|industry survey|https://example.com/research&#10;Perplexity|guide|https://example.com/guide"></textarea>
        </div>
        <div>
          <label>8) Historical Ground-Truth Corpora (internal brand docs)</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">
            PDF / whitepaper / Markdown file paths so the tool can compare the
            Internal Brand Perception Vector vs the Web RAG Vector. One per line.</div>
          <textarea name="corpus_files" placeholder="C:\docs\acme-whitepaper.pdf&#10;C:\docs\product-specs.txt"></textarea>
        </div>
      </div>
      <div class="row" style="margin-top:12px;">
        <div>
          <label>11) Competitor Content Change Logs — RSS / sitemap feeds</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">Competitor / industry feeds ingested in near-real-time for freshness.</div>
          <textarea name="content_feeds" placeholder="https://competitor.com/feed.xml&#10;https://competitor.com/sitemap.xml"></textarea>
        </div>
        <div>
          <label>11b) Local corpus directory (ground-truth folder)</label>
          <div class="hint" style="margin:2px 0 8px;font-size:12px;">Alternative to per-file list — point at an entire internal docs folder.</div>
          <input type="text" name="corpus_dir" placeholder="./sample_corpus">
        </div>
      </div>
      <div class="row" style="margin-top:12px;">
        <div>
          <label>Synthetic query count</label>
          <input type="number" name="synthetic_query_count" value="12" min="0" max="100">
        </div>
        <div>
          <label>Chunk/target density settings</label>
          <div style="display:flex;gap:8px;">
            <input type="number" name="chunk_tokens" value="512" min="64" max="8192" title="Chunk tokens">
            <input type="number" name="target_entity_density" value="0.015" step="0.001" min="0" max="1" title="Target entity density">
            <input type="number" name="top_k_retrieval" value="5" min="1" max="50" title="Top-k retrieval">
          </div>
          <div class="hint" style="margin:4px 0 0;font-size:11px;">chunk tokens · target entity density · top-k</div>
        </div>
      </div>
      <div class="row" style="margin-top:12px;">
        <div>
          <label>9) Target Embedding Model Selection</label>
          <input type="text" name="embedding_model" value="sentence-transformers/all-MiniLM-L6-v2">
          <div class="hint" style="margin:4px 0 0;font-size:11px;">
            Pick the embedding architecture matching the AI engine's vector space
            (e.g. <code>bge-large-en-v1.5</code>, <code>all-MiniLM-L6-v2</code>).
            Operator is responsible for supplying a local model.</div>
        </div>
        <div>
          <label>Ollama model (optional local LLM)</label>
          <input type="text" name="ollama_model" value="llama3">
          <div class="hint" style="margin:4px 0 0;font-size:11px;">Ollama base URL:</div>
          <input type="text" name="ollama_base_url" placeholder="http://localhost:11434">
        </div>
      </div>
    </div>
  </div>

  <button type="submit" class="primary" id="runBtn">▶ Run Full Audit</button>
  <div id="status"></div>

  <div class="barwrap" id="barwrap" style="display:none">
    <div class="barlabel"><span id="stage">Initializing…</span><span id="timer">00:00</span></div>
    <div class="bar"><div class="barfill" id="barfill"></div></div>
  </div>

  <div id="console"></div>
</form>
</div>

<div id="page-features" class="page"></div>
<div id="page-outputs" class="page"></div>

<script>
// ---- theme toggle ----
const themeBtn = document.getElementById('themeBtn');
function applyTheme(t){
  if(t==='light'){ document.body.classList.add('light'); themeBtn.textContent='☀️ Light'; }
  else { document.body.classList.remove('light'); themeBtn.textContent='🌙 Dark'; }
}
applyTheme(localStorage.getItem('ragevda-theme')||'dark');
themeBtn.onclick = () => {
  const next = document.body.classList.contains('light') ? 'dark':'light';
  localStorage.setItem('ragevda-theme', next); applyTheme(next);
};

const adv = document.getElementById('advToggle');
adv.onclick = () => {
  const p = document.getElementById('advPanel');
  p.style.display = p.style.display === 'none' ? 'block' : 'none';
  adv.textContent = (p.style.display === 'none' ? '▸' : '▾') + ' Advanced options (harvester, models)';
};

function splitList(s){ return s.split(/[\n,]/).map(x=>x.trim()).filter(Boolean); }

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
  const consoleEl=document.getElementById('console');
  const statusEl=document.getElementById('status');
  const barwrap=document.getElementById('barwrap');
  consoleEl.style.display='block'; consoleEl.textContent='';
  barwrap.style.display='block';
  statusEl.textContent='Queued — starting live audit…';
  startTs=Date.now();
  document.getElementById('barfill').style.width='4%';
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
  fetch('/status/'+jobId).then(r=>r.json()).then(d=>{
    if(d.logs) document.getElementById('console').textContent = d.logs.join('\n');
    const c=document.getElementById('console'); c.scrollTop=c.scrollHeight;
    if(typeof d.progress==='number'){ document.getElementById('barfill').style.width=Math.max(4,d.progress)+'%'; }
    if(d.stage) document.getElementById('stage').textContent=d.stage;
    if(d.status==='done'){ finish(jobId); return; }
    if(d.status==='error'){ document.getElementById('status').innerHTML='<span class="err">Error: '+d.error+'</span>'; stopTimers(); return; }
    document.getElementById('status').textContent='Running… ('+d.progress+'%)';
    pollTimer=setTimeout(()=>poll(jobId), 1000);
  }).catch(()=>{ pollTimer=setTimeout(()=>poll(jobId), 1500); });
}

function stopTimers(){ if(pollTimer) clearTimeout(pollTimer); if(tickTimer) clearInterval(tickTimer); }

function finish(jobId){
  stopTimers();
  document.getElementById('barfill').style.width='100%';
  document.getElementById('stage').textContent='Complete';
  document.getElementById('status').textContent='Audit complete — opening analysis.';
  document.getElementById('runBtn').disabled=false;
  document.getElementById('page-inputs').classList.remove('active');
  loadFeatures(jobId);
}

function setStep(id, state){
  const el=document.getElementById(id);
  if(!el) return;
  el.classList.remove('active','done');
  if(state) el.classList.add(state);
}

function loadFeatures(jobId){
  const el=document.getElementById('page-features');
  el.innerHTML='<div class="card">Loading analysis…</div>';
  setStep('step1','done'); setStep('step2','active');
  el.classList.add('active');
  fetch('/page/features/'+jobId).then(r=>r.text()).then(h=>{
    el.innerHTML = h + '<div class="nav-btns"><button class="btn-ghost" onclick="loadOutputs(\''+jobId+'\')">Continue to Outputs →</button></div>';
    window.scrollTo(0,0);
  }).catch(()=>{ el.innerHTML='<div class="card err">Failed to load analysis.</div>'; });
}

function loadOutputs(jobId){
  const el=document.getElementById('page-outputs');
  el.innerHTML='<div class="card">Loading outputs…</div>';
  setStep('step2','done'); setStep('step3','active');
  document.getElementById('page-features').classList.remove('active');
  el.classList.add('active');
  fetch('/page/outputs/'+jobId).then(r=>r.text()).then(h=>{
    el.innerHTML = h + '<div class="nav-btns"><button class="btn-ghost" onclick="backToFeatures()">← Back to Analysis</button></div>';
    window.scrollTo(0,0);
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
</body></html>"""


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def _start_run(profile: dict) -> str:
    """Build a RunConfig from a profile dict and launch a background audit.

    Returns the new job id. Used by both the UI ('/run') and the scheduler, so
    scheduled runs land in the same ``web_output/jobs`` store and appear in
    History/Trends automatically.
    """
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
                                       "Google AI Overviews, SearchGPT, Gemini, Perplexity, Bing Copilot").split(",")
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
        content_feeds=feed_list,
        serp_footprints=serp_footprints,
        chunk_tokens=_int(profile.get("chunk_tokens"), 512),
        chunk_overlap_tokens=_int(profile.get("chunk_overlap_tokens"), 64),
        target_entity_density=_float(profile.get("target_entity_density"), 0.015),
        top_k_retrieval=_int(profile.get("top_k_retrieval"), 5),
        engine_matrix=engine_list,
        ollama_base_url=profile.get("ollama_base_url") or None,
        ollama_model=profile.get("ollama_model") or "llama3",
        synthetic_query_count=_int(profile.get("synthetic_query_count"), 12),
        output_dir=os.path.join(WEB_OUTPUT, "jobs", "temp"),
    )
    job_id = datetime.utcnow().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    job_dir = os.path.join(WEB_OUTPUT, "jobs", job_id)
    os.makedirs(job_dir, exist_ok=True)
    cfg.output_dir = job_dir
    JOBS[job_id] = {
        "status": "running", "logs": [], "progress": 2,
        "stage": "Queued", "dir": job_dir, "error": "",
    }
    threading.Thread(target=_worker, args=(job_id, cfg), daemon=True).start()
    return job_id


_PAGE_CSS = """
:root{
  --bg:#0b0e14; --bg2:#0e1320; --surface:#141a28; --surface2:#1b2233; --border:#28324c;
  --text:#e8ecf4; --muted:#94a3c4; --accent:#6d8bff; --accent2:#34d399;
  --good:#34d399; --warn:#fbbf24; --bad:#fb7185; --radius:16px;
  --shadow:0 12px 34px rgba(0,0,0,.45); --shadow-sm:0 4px 16px rgba(0,0,0,.30);
  --ring:0 0 0 4px rgba(109,139,255,.22);
  --font:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --display:'Sora',var(--font);
}
* { box-sizing:border-box; }
body{ margin:0; color:var(--text); font-family:var(--font); font-size:14px; line-height:1.65;
  -webkit-font-smoothing:antialiased; letter-spacing:.1px;
  background:
    radial-gradient(1200px 620px at 10% -12%, rgba(109,139,255,.14), transparent 60%),
    radial-gradient(1000px 520px at 102% -4%, rgba(52,211,153,.10), transparent 55%),
    var(--bg); }
.wrap{ max-width:1120px; margin:0 auto; padding:26px 24px 56px; }
.topnav{ display:flex; gap:10px; margin-bottom:18px; flex-wrap:wrap; }
.topnav a{ background:rgba(255,255,255,.03); border:1px solid var(--border); color:var(--text);
  padding:9px 16px; border-radius:12px; font-size:13px; text-decoration:none; font-weight:600; transition:.18s; }
.topnav a:hover{ border-color:var(--accent); color:#fff; transform:translateY(-1px); box-shadow:var(--shadow-sm); }
h2{ display:flex; align-items:center; gap:9px; font-family:var(--display); font-size:18px; font-weight:700;
  color:var(--text); margin:30px 0 12px; letter-spacing:-.2px; }
h2::before{ content:""; width:4px; height:18px; border-radius:3px;
  background:linear-gradient(180deg,var(--accent),var(--accent2)); }
section{ margin:0; }
table{ width:100%; border-collapse:separate; border-spacing:0; margin-top:10px; font-size:13px;
  background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; }
th,td{ text-align:left; padding:11px 13px; border-bottom:1px solid var(--border); vertical-align:top; }
th{ color:var(--muted); text-transform:uppercase; font-size:10.5px; letter-spacing:.6px;
  background:var(--surface2); font-weight:600; }
tbody tr:last-child td{ border-bottom:none; }
tbody tr:nth-child(even){ background:rgba(255,255,255,.02); }
tbody tr:hover{ background:rgba(109,139,255,.06); }
.row-good{ background:rgba(52,211,153,.12) !important; }
.row-bad{ background:rgba(251,113,133,.14) !important; }
.kpis{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:16px; margin-top:12px; }
.kpi{ background:linear-gradient(180deg,var(--surface2),var(--surface)); border:1px solid var(--border);
  border-radius:var(--radius); padding:16px 18px; box-shadow:var(--shadow-sm); }
.kpi .v{ font-family:var(--display); font-size:28px; font-weight:800; }
.kpi .l{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.6px; margin-top:4px; }
select,input,textarea{ background:var(--bg); color:var(--text); border:1px solid var(--border);
  border-radius:12px; padding:9px 11px; font-size:13px; font-family:inherit; transition:.15s; }
select:focus,input:focus,textarea:focus{ outline:none; border-color:var(--accent); box-shadow:var(--ring); }
textarea{ width:100%; min-height:64px; resize:vertical; }
.inline{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:8px 0; }
label{ color:var(--muted); font-size:12px; margin-right:4px; }
button,input[type=submit]{ background:linear-gradient(92deg,var(--accent),var(--accent2)); color:#06121f;
  border:none; padding:10px 18px; border-radius:13px; cursor:pointer; font-size:13px; font-weight:800;
  box-shadow:0 8px 22px rgba(52,211,153,.26); transition:.18s; }
button:hover{ transform:translateY(-1px); filter:brightness(1.05); }
.muted{ color:var(--muted); }
.footer{ color:var(--muted); font-size:12.5px; margin-top:16px; line-height:1.6; }
.card{ background:linear-gradient(180deg,var(--surface),var(--bg2)); border:1px solid var(--border);
  border-radius:var(--radius); padding:16px 18px; margin-top:14px; box-shadow:var(--shadow-sm); }
code{ background:rgba(255,255,255,.06); padding:1px 6px; border-radius:6px; font-size:12px; }
body.light{ --bg:#f5f8fc; --bg2:#ffffff; --surface:#ffffff; --surface2:#eef2f8; --border:#dde4ef;
  --text:#0f172a; --muted:#5b6b86; --shadow:0 12px 34px rgba(20,40,80,.10);
  --shadow-sm:0 4px 16px rgba(20,40,80,.08); --ring:0 0 0 4px rgba(109,139,255,.20); }
body.light .card,body.light table{ box-shadow:var(--shadow-sm); }
"""


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — RAG-EVDA</title><style>{_PAGE_CSS}</style></head>
<body><div class="wrap">
<nav class="topnav"><a href="/">🏠 Audit</a>
<a href="/history">📈 History &amp; Trends</a>
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
      <div class="kpi"><div class="v" style="color:#1abc9c">{latest.composite_sov}%</div>
        <div class="l">Latest Vector SoV</div></div>
      <div class="kpi"><div class="v" style="color:#e67e22">{latest.rag_invisibility_index}%</div>
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
          <input name="name" placeholder="Weekly cricket check" style="min-width:200px"></div>
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
            <input name="corpus_dir" placeholder="./sample_corpus" style="min-width:180px"></div>
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
    app = Flask(__name__)

    @app.route("/")
    def index():
        return INDEX_HTML

    @app.route("/run", methods=["POST"])
    def run_audit():
        form = request.form
        profile = {
            "target_brand": form.get("target_brand"),
            "industry_topics": [t.strip() for t in
                                form.get("industry_topics", "").replace("\n", ",").split(",") if t.strip()],
            "competitor_entities": [c.strip() for c in
                                    form.get("competitor_entities", "").replace("\n", ",").split(",") if c.strip()],
            "crawl_depth": form.get("crawl_depth") or 50,
            "locality": form.get("locality") or "",
            "harvester": form.get("harvester") or "duckduckgo",
            "prefer_searxng": form.get("prefer_searxng") is not None,
            "searxng_base_url": form.get("searxng_base_url") or "",
            "corpus_dir": form.get("corpus_dir") or "",
            "embedding_model": form.get("embedding_model") or "sentence-transformers/all-MiniLM-L6-v2",
            "spacy_model": form.get("spacy_model") or "en_core_web_sm",
            "auto_threshold": form.get("auto_threshold") is not None,
            "high_relevance_threshold": form.get("high_relevance_threshold") or 0.70,
            "search_intent": form.get("search_intent") or "informational",
            "engine_matrix": form.get("engine_matrix") or "",
            "ontology_aliases": form.get("ontology_aliases") or "",
            "entity_weighting": form.get("entity_weighting") or "",
            "query_templates": form.get("query_templates") or "",
            "corpus_files": form.get("corpus_files") or "",
            "serp_footprints": form.get("serp_footprints") or "",
            "content_feeds": form.get("content_feeds") or "",
            "chunk_tokens": form.get("chunk_tokens") or 512,
            "chunk_overlap_tokens": form.get("chunk_overlap_tokens") or 64,
            "target_entity_density": form.get("target_entity_density") or 0.015,
            "top_k_retrieval": form.get("top_k_retrieval") or 5,
            "synthetic_query_count": form.get("synthetic_query_count") or 12,
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
        j = JOBS.get(job)
        if not j:
            return Response(json.dumps({"status": "not_found"}), mimetype="application/json")
        return Response(json.dumps({
            "status": j["status"],
            "progress": j["progress"],
            "stage": j["stage"],
            "logs": j["logs"],
            "error": j["error"],
        }), mimetype="application/json")

    @app.route("/files/<job>/<path:filename>")
    def files(job: str, filename: str):
        job_dir = os.path.join(WEB_OUTPUT, "jobs", job)
        # Lazily build the enterprise PDF on first request, then serve it.
        if filename == "report.pdf" and not os.path.exists(os.path.join(job_dir, "report.pdf")):
            data = _load_job_data(job)
            if data is not None:
                try:
                    from .reporting.pdf_report import render_report_pdf
                    render_report_pdf(data, job, os.path.join(job_dir, "report.pdf"))
                except Exception as exc:  # noqa: BLE001
                    logger.exception("PDF generation failed")
                    return Response(f"PDF generation failed: {exc}", status=500)
        return send_from_directory(job_dir, filename)

    @app.route("/page/features/<job>")
    def page_features(job: str):
        data = _load_job_data(job)
        if data is None:
            return Response("<p class='muted'>Job not found.</p>", mimetype="text/html")
        return Response(_narrative.features_html(data), mimetype="text/html")

    @app.route("/page/outputs/<job>")
    def page_outputs(job: str):
        data = _load_job_data(job)
        if data is None:
            return Response("<p class='muted'>Job not found.</p>", mimetype="text/html")
        return Response(_narrative.outputs_html(data, job), mimetype="text/html")

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
            sid = datetime.utcnow().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]
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
                prefer_searxng=form.get("prefer_searxng") is not None,
                searxng_base_url=form.get("searxng_base_url") or None,
                corpus_dir=form.get("corpus_dir") or None,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                spacy_model="en_core_web_sm",
                auto_threshold=form.get("auto_threshold") is not None,
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
        j["logs"].append("Audit complete.")
        j["progress"] = 100
        j["stage"] = "Complete"
        j["status"] = "done"
    except Exception as exc:  # noqa: BLE001
        logger.exception("audit failed")
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
