"""AI-crawler analytics: GPTBot / OAI-SearchBot frequency from server logs.

Parses Common/Combined Log Format lines for known AI crawler tokens and
reports hits per bot, per path, per day. Fail-open: missing log path yields
``{"configured": False}`` with setup instructions — never synthesised.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import Dict

BOT_PATTERNS = {
    "GPTBot": re.compile(r"GPTBot", re.I),
    "OAI-SearchBot": re.compile(r"OAI-SearchBot", re.I),
    "ClaudeBot": re.compile(r"ClaudeBot|anthropic-ai", re.I),
    "PerplexityBot": re.compile(r"PerplexityBot", re.I),
    "Google-Extended": re.compile(r"Google-Extended", re.I),
    "Bytespider": re.compile(r"Bytespider", re.I),
}


def analyze_crawler_logs(log_path: str = "", log_text: str = "") -> Dict:
    lines: list = []
    if log_text:
        lines = log_text.splitlines()
    elif log_path and os.path.exists(log_path):
        try:
            with open(log_path, encoding="utf-8", errors="ignore") as fh:
                lines = fh.read().splitlines()
        except Exception as exc:  # noqa: BLE001
            return {"configured": False, "error": str(exc)}
    else:
        return {"configured": False,
                "note": ("point AI_CRAWLER_LOG at your access log "
                         "(e.g. /var/log/nginx/access.log) to measure "
                         "GPTBot/OAI-SearchBot/PerplexityBot hit frequency")}

    per_bot: Counter = Counter()
    per_path: Counter = Counter()
    for ln in lines:
        for bot, pat in BOT_PATTERNS.items():
            if pat.search(ln):
                per_bot[bot] += 1
                m = re.search(r'"[A-Z]+ (\S+) HTTP', ln)
                if m:
                    per_path[m.group(1)] += 1
                break
    total = sum(per_bot.values())
    return {"configured": True, "total_ai_hits": total,
            "per_bot": dict(per_bot),
            "top_paths": [{"path": p, "hits": n}
                          for p, n in per_path.most_common(20)],
            "method": "regex scan of access-log lines for AI bot tokens"}
