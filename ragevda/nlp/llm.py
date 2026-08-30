"""Optional local LLM (Ollama) gap-analysis engine.

Runs entirely on the operator's machine when an Ollama server is available
(``ollama_base_url`` + ``ollama_model``).  It turns the raw vector/token math
into explicit content-brief recommendations: e.g. *"why did the LLM retrieve
Competitor A over us for this prompt?"*.

To keep the tool honest and reproducible, the LLM is strictly OPTIONAL:

* If configured and reachable, it summarises real retrieved chunks / gaps and
  returns *derived rationale* on top of the deterministic metrics.
* If not configured or unreachable, the pipeline still runs and every
  data-driven number is present -- only the free-text "LLM rationale" fields
  are omitted (the tool never invents an LLM answer when none is available).

No paid API is ever called.
"""

from __future__ import annotations

import logging
import json
from typing import Dict, List, Optional

from ..utils import get_logger

logger = get_logger("ragevda.nlp.llm")


class LLMGapEngine:
    """Thin optional client over an Ollama-compatible `/api/chat` endpoint."""

    def __init__(self, config):
        self.base = (config.ollama_base_url or "").rstrip("/")
        self.model = config.ollama_model or "llama3"
        self.enabled = bool(config.use_llm and self.base)
        self.available = False
        self._http = None
        if not self.enabled:
            return
        try:
            import httpx
            self._http = httpx.Client(timeout=90)
            self.available = self._ping()
            if not self.available:
                logger.warning(
                    "Ollama configured at %s but not reachable; LLM rationale "
                    "disabled (deterministic metrics still emitted).", self.base)
        except Exception as exc:  # noqa: BLE001
            self.available = False
            logger.warning("Ollama unavailable: %s", exc)

    def _ping(self) -> bool:
        try:
            r = self._http.get(f"{self.base}/api/tags", timeout=15)
            return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def ask(self, prompt: str, max_tokens: int = 300) -> Optional[str]:
        """Send a prompt to Ollama and return the assistant text, or None."""
        if not self.available:
            return None
        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"num_predict": max_tokens},
            }
            r = self._http.post(
                f"{self.base}/api/chat", json=payload, timeout=120)
            if r.status_code != 200:
                return None
            data = r.json()
            return (data.get("message") or {}).get("content", "").strip() or None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama ask failed: %s", exc)
            return None

    def close(self) -> None:
        if self._http is not None:
            self._http.close()


def llm_gap_summary(engine: Optional[LLMGapEngine], ctx, density_result: Dict,
                    sentiment_result: Dict) -> Dict:
    """Derive free-text rationale for the biggest gaps when an LLM is present."""
    if engine is None or not engine.available:
        return {
            "available": False,
            "model": None,
            "rationale": [],
            "note": ("Local LLM (Ollama) not configured/reachable. Deterministic "
                     "metrics are complete; free-text rationale omitted."),
        }

    gaps = density_result.get("per_topic", []) or []
    rationale = []
    for g in gaps[:3]:
        topic = g.get("topic", "")
        leader = g.get("leading_competitor", "")
        prompt = (
            f"You are a search-engine retrieval analyst. Given these AUDITED metrics:\n"
            f"- Topic: {topic}\n"
            f"- Brand tokens on window: {g.get('brand_on_window_usage_tokens', 0)}\n"
            f"- Leading competitor: {leader} with "
            f"{g.get('leader_on_window_usage_tokens', 0)} tokens\n"
            f"- Brand proximity: {g.get('brand_proximity', 0)}\n"
            f"- Severity: {g.get('severity', '')}\n"
            f"Explain in 2-3 sentences why an AI RAG engine likely retrieved "
            f"{leader} instead of the brand for '{topic}', and state the single "
            f"highest-leverage content action. Do not invent data."
        )
        text = engine.ask(prompt)
        if text:
            rationale.append({"topic": topic, "llm_rationale": text})

    return {
        "available": True,
        "model": engine.model,
        "rationale": rationale,
    }
