"""Repeat-run scheduler for automated real-time tracking.

Lets a user save an "audit profile" (brand + topics + competitors + settings) and
have the tool re-run it on an interval (e.g. every 6 hours) without manual clicks.
Each scheduled run writes a normal ``web_output/jobs/<jobid>`` report, so it is
automatically picked up by the history/trend engine -- that is what produces the
"time" dimension of "real-time tracking".

Schedules are persisted to ``web_output/schedules.json``. A single background
thread (started by the web app) polls every 20s and fires due profiles.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from .utils import get_logger

logger = get_logger("ragevda.scheduler")

DEFAULT_SCHEDULES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "web_output", "schedules.json",
)
DEFAULT_INTERVAL_MIN = 360  # 6 hours


@dataclass
class Schedule:
    id: str
    name: str
    brand: str
    topics: List[str]
    competitors: List[str]
    interval_minutes: int = DEFAULT_INTERVAL_MIN
    enabled: bool = True
    depth: int = 50
    locality: Optional[str] = None
    harvester: str = "duckduckgo"
    prefer_searxng: bool = False
    searxng_base_url: Optional[str] = None
    corpus_dir: Optional[str] = None
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    spacy_model: str = "en_core_web_sm"
    auto_threshold: bool = True
    high_relevance_threshold: float = 0.70
    search_intent: str = "informational"
    chunk_tokens: int = 512
    chunk_overlap_tokens: int = 64
    max_pages: int = 200               # 0 = unlimited page fetches
    max_search_queries: int = 120      # 0 = unlimited search calls
    engine_matrix: List[str] = field(default_factory=lambda: [
        "Google AI Overviews", "SearchGPT", "Gemini", "Perplexity", "Bing Copilot"])
    last_run: Optional[str] = None
    last_job: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def next_run(self) -> Optional[datetime]:
        base = self.last_run or self.created_at
        try:
            dt = datetime.strptime(base, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            # Corrupt timestamp: do NOT collapse to datetime.min (would fire
            # in a tight loop). Schedule one full interval from now instead.
            logger.warning("corrupt schedule timestamp %r; delaying one interval", base)
            return datetime.now(timezone.utc) + timedelta(
                minutes=max(1, self.interval_minutes)
            )
        return dt + timedelta(minutes=max(1, self.interval_minutes))

    def profile(self) -> Dict:
        return {
            "target_brand": self.brand,
            "industry_topics": self.topics,
            "competitor_entities": self.competitors,
            "crawl_depth": self.depth,
            "locality": self.locality,
            "harvester": self.harvester,
            "prefer_searxng": self.prefer_searxng,
            "searxng_base_url": self.searxng_base_url,
            "corpus_dir": self.corpus_dir,
            "embedding_model": self.embedding_model,
            "spacy_model": self.spacy_model,
            "auto_threshold": self.auto_threshold,
            "high_relevance_threshold": self.high_relevance_threshold,
            "search_intent": self.search_intent,
            "chunk_tokens": self.chunk_tokens,
            "chunk_overlap_tokens": self.chunk_overlap_tokens,
            "engine_matrix": ",".join(self.engine_matrix),
            "require_real_models": True,
            "use_llm": True,
            "dedupe_near": True,
            "max_pages": self.max_pages,
            "max_search_queries": self.max_search_queries,
            "drift_history_keep": 60,
        }


class Scheduler:
    def __init__(self, path: str = DEFAULT_SCHEDULES_FILE) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._schedules: Dict[str, Schedule] = {}
        self._callback: Optional[Callable[[Dict], Optional[str]]] = None
        self._load()

    # ---- persistence ----------------------------------------------------
    def _load(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for s in data.get("schedules", []):
                try:
                    self._schedules[s["id"]] = Schedule(**s)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("bad schedule entry: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not load schedules: %s", exc)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"schedules": [asdict(s) for s in self._schedules.values()]},
                      fh, indent=2)

    # ---- API ------------------------------------------------------------
    def add(self, sched: Schedule) -> Schedule:
        with self._lock:
            self._schedules[sched.id] = sched
            self._save()
        logger.info("schedule added: %s (%s)", sched.id, sched.name)
        return sched

    def remove(self, sid: str) -> bool:
        with self._lock:
            if sid in self._schedules:
                del self._schedules[sid]
                self._save()
                return True
        return False

    def list(self) -> List[Schedule]:
        with self._lock:
            return sorted(self._schedules.values(), key=lambda s: s.created_at)

    def get(self, sid: str) -> Optional[Schedule]:
        with self._lock:
            return self._schedules.get(sid)

    # ---- engine ---------------------------------------------------------
    def start(self, callback: Callable[[Dict], Optional[str]]) -> None:
        self._callback = callback
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        logger.info("scheduler background thread started")

    def _loop(self) -> None:
        while True:
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001
                logger.warning("scheduler tick error: %s", exc)
            threading.Event().wait(20)

    def tick(self) -> List[str]:
        """Fire any enabled schedules whose next_run is due. Returns job ids."""
        if not self._callback:
            return []
        fired: List[str] = []
        now = datetime.now(timezone.utc)
        with self._lock:
            due = [s for s in self._schedules.values()
                   if s.enabled and (s.next_run() or now) <= now]
        for s in due:
            try:
                job = self._callback(s.profile())
                s.last_run = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                s.last_job = job
                with self._lock:
                    self._save()
                fired.append(job or "")
                logger.info("scheduled run fired for %s -> job %s", s.name, job)
            except Exception as exc:  # noqa: BLE001
                logger.warning("scheduled run failed (%s): %s", s.name, exc)
        return fired
