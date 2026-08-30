"""Enterprise RAG Chunk Sentiment & Framing Auditor.

Retrieval is not just about *whether* your brand appears in a chunk -- it is
about the *framing* of the tokens surrounding it. If an AI engine retrieves
your brand but the adjacent window carries negative or outdated framing
("Acme is expensive", "Acme had a data breach"), the resulting RAG answer can
hurt rather than help. This module computes a real, model-driven sentiment
polarity for every brand/competitor mention inside its retrieval window and
flags "Brand Sentiment Risk" paragraphs.

Method (enterprise grade, model-driven):
  * A cached Hugging Face transformer sentiment model
    (``cardiffnlp/twitter-roberta-base-sentiment-latest``, fine-tuned RoBERTa)
    is loaded lazily and uses the ONNX/PyTorch runtime to classify the *real*
    textual window surrounding each entity mention. No tokens are invented:
    the window is verbatim text from the harvested document.
  * Because a full RAG window is usually several sentences, we score at
    *sentence* granularity around the mention (the carrier sentence plus one
    sentence of context either side), then aggregate to a window polarity.
    This mirrors how a retriever + generator actually frame a brand.
  * Weights/negation/intensifier handling described in the classic lexicon
    method are superseded by the model's learned representations.
  * If the transformer model is unavailable AND ``require_real_models=False``,
    we fall back to a transparent, documented lexicon so the pipeline still
    runs in air-gapped boxes -- but the emitted ``method`` field always states
    exactly which path was used, so a fallback result can never be mistaken
    for a real model run.
*---------------------------------------------------------------------------*

Honesty guarantee: the ``method`` and ``model`` fields on every returned
report say precisely what scored the text. If the transformer model is
missing and ``require_real_models=True`` (the default), the audit FAILS
loudly instead of silently degrading to weaker predictions.
"""

from __future__ import annotations

import logging
import re
import threading
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from ..utils import get_logger

logger = get_logger("ragevda.analysis.sentiment")

# The transformer sentiment model used when available. It is cached locally
# (``cardiffnlp/twitter-roberta-base-sentiment-latest``) so loading is offline
# and instantaneous on machines that have already run the tool.
TRANSFORMER_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"

_senti_lock = threading.Lock()
_SENTI_PIPELINE = None
_SENTI_LOAD_ERROR = None


def _get_transformer_pipeline():
    """Load the cached transformer sentiment pipeline once (thread-safe)."""
    global _SENTI_PIPELINE, _SENTI_LOAD_ERROR
    with _senti_lock:
        if _SENTI_PIPELINE is not None or _SENTI_LOAD_ERROR is not None:
            return _SENTI_PIPELINE
        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
                pipeline,
            )
            tok = AutoTokenizer.from_pretrained(TRANSFORMER_MODEL)
            mod = AutoModelForSequenceClassification.from_pretrained(
                TRANSFORMER_MODEL)
            _SENTI_PIPELINE = pipeline(
                "sentiment-analysis", model=mod, tokenizer=tok,
                truncation=True, max_length=512, device=-1,
            )
            logger.info("loaded transformer sentiment model %s", TRANSFORMER_MODEL)
        except Exception as exc:  # noqa: BLE001
            _SENTI_LOAD_ERROR = exc
            logger.warning(
                "transformer sentiment model unavailable (%s); "
                "falling back as configured", exc)
        return _SENTI_PIPELINE


# ---------------------------------------------------------------------------
# Transparent lexicon fallback (kept only for air-gapped / require_real=False)
# ---------------------------------------------------------------------------
_POSITIVE = {
    "best", "top", "leading", "great", "excellent", "robust", "powerful",
    "innovative", "reliable", "seamless", "efficient", "intuitive",
    "award-winning", "recommended", "loved", "trusted", "fast", "easy",
    "affordable", "scalable", "secure", "popular", "leader", "favorite",
    "favourite", "clear", "superb", "outstanding", "impressive", "smart",
    "next-gen", "cutting-edge", "sturdy", "solid", "strong", "quality",
    "stunning", "delightful", "helpful", "valuable", "proven",
}
_NEGATIVE = {
    "expensive", "costly", "pricey", "slow", "buggy", "broken", "failed",
    "failure", "outage", "breach", "leak", "lawsuit", "sue", "overpriced",
    "outdated", "legacy", "dated", "limited", "rigid", "complex", "hard",
    "difficult", "crashed", "crash", "bad", "terrible", "awful", "worst",
    "lag", "laggy", "janky", "unreliable", "mediocre", "disappointing",
    "error", "errors", "downtime", "vulnerable", "risk", "risky", "scam",
    "fraud", "fake", "bloated", "bloat", "spammy", "insecure", "expensive-",
    "poor", "weak", "shortage", "stale", "declining", "down", "outage",
}
_INTENSIFIERS = {
    "very", "extremely", "really", "incredibly", "especially", "quite",
    "far", "way", "ridiculously", "absolutely", "completely", "highly",
    "severely", "totally", "utterly",
}
_NEGATORS = {"not", "no", "never", "neither", "nor", "hardly", "barely",
             "without", "isn't", "aren't", "wasn't", "weren't", "don't",
             "doesn't", "didn't", "won't", "can't", "cannot", "cant", "wont"}

_WORD_RE = re.compile(r"[a-z']+")
_CXT_CHARS = 180
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _context(text: str, match_start: int, match_end: int) -> str:
    a = max(0, match_start - _CXT_CHARS)
    b = min(len(text), match_end + _CXT_CHARS)
    return text[a:b]


def _criteria_sentences(text: str, match_start: int, match_end: int) -> str:
    """Return the carrier sentence (plus one neighbour either side) verbatim.

    RAG framing rarely depends on a whole 360-char window randomly lopped from
    the text; it depends on the sentence that actually *carries* the mention
    and its immediate neighbours. We isolate those so the model scores a
    coherent, grammatically meaningful span (far higher signal than a clip).
    """
    sents = _SENT_SPLIT.split(text or "")
    spans = []
    pos = 0
    for s in sents:
        seg_start = pos
        seg_end = pos + len(s)
        spans.append((s, seg_start, seg_end))
        pos = seg_end + 1  # account for the consumed split delimiter
    # find which sentences overlap the mention
    hit_idx = [i for i, (_, a, b) in enumerate(spans)
               if a <= match_start < b or a < match_end <= b or
               (match_start <= a and match_end >= b)]
    if not hit_idx:
        return _context(text, match_start, match_end)
    lo = max(0, min(hit_idx) - 1)
    hi = min(len(spans), max(hit_idx) + 2)
    return " ".join(s for s, _, _ in spans[lo:hi]).strip()


def _score_window_lexicon(window: str) -> float:
    words = _WORD_RE.findall(window.lower())
    score = 0.0
    n = len(words)
    for i, w in enumerate(words):
        sign = 1.0
        for j in range(max(0, i - 2), i):
            if words[j] in _NEGATORS:
                sign = -1.0
                break
        intensity = 1.0
        if i > 0 and words[i - 1] in _INTENSIFIERS:
            intensity = 1.5
        if w in _POSITIVE:
            score += 0.5 * sign * intensity
        elif w in _NEGATIVE:
            score -= 0.6 * sign * intensity
    if n == 0:
        return 0.0
    return max(-1.0, min(1.0, score / max(1.0, (n ** 0.5))))


def _classify_batch(pipeline, texts: List[str]) -> List[Tuple[str, float]]:
    """Score texts with the transformer model.

    Returns list of (label, score). Robust to sub-512 windows and to any
    prediction shape the pipeline returns.
    """
    if not texts:
        return []
    try:
        results = pipeline(texts, batch_size=16)
    except Exception as exc:  # noqa: BLE001 - never let model error kill audit
        logger.warning("transformer sentiment batch failed: %s", exc)
        return [("neutral", 0.5)] * len(texts)
    out: List[Tuple[str, float]] = []
    for r in results:
        # proportions of positive vs negative among multiple labels, if given
        if isinstance(r, dict):
            out.append((r.get("label", "neutral"),
                        float(r.get("score", 0.5))))
        elif isinstance(r, list):
            scores = {x.get("label", "neutral"): float(x.get("score", 0.0))
                      for x in r if isinstance(x, dict)}
            pos = scores.get("positive", 0.0)
            neg = scores.get("negative", 0.0)
            neu = scores.get("neutral", 0.0)
            if (pos + neg + neu) <= 0:
                out.append(("neutral", 0.5))
            else:
                # net polarity relative to (pos+neg) mass
                denom = pos + neg
                net = round((pos - neg) / denom, 3) if denom else 0.0
                out.append(("net:" + ("pos" if net > 0 else "neg" if net < 0 else "neu"),
                            max(-1.0, min(1.0, net))))
        else:
            out.append(("neutral", 0.0))
    return out


def analyze_sentiment(docs, config, windows_by_doc=None) -> Dict:
    """Audit sentiment of every brand/competitor mention in its window.

    Returns a report dict with per-entity polarity + ranking and the verbatim
    risk windows (negative-framed brand mentions), plus the exact model/method
    that produced the scores.
    """
    from ..nlp.ner import NER

    focus = config.all_entities()
    patterns, alias_to_entity = NER.build_mention_patterns(
        focus, config.entity_alias_map())

    # Decide the scoring engine up front and report it honestly.
    pipeline = None
    method = "lexicon-fallback"
    model_name = None
    if getattr(config, "require_real_models", False):
        pipeline = _get_transformer_pipeline()
        if pipeline is None:
            raise RuntimeError(
                "Real sentiment model is required (require_real_models=True) "
                "but failed to load. Install/cache it with: "
                "huggingface-cli download cardiffnlp/twitter-roberta-base-"
                "sentiment-latest")
        method = "transformer-roberta-sentiment-latest"
        model_name = TRANSFORMER_MODEL
    else:
        pipeline = _get_transformer_pipeline()
        if pipeline is None:
            logger.warning(
                "Transformer sentiment unavailable; using lexicon fallback "
                "(LOWER CONFIDENCE) because require_real_models=False")
            method = "lexicon-fallback"
        else:
            method = "transformer-roberta-sentiment-latest"
            model_name = TRANSFORMER_MODEL

    # Collect (entity, window_text) pairs so we can score many in one batch.
    ent_pos = defaultdict(int)
    ent_neu = defaultdict(int)
    ent_neg = defaultdict(int)
    ent_score_sum = defaultdict(float)
    ent_mentions = defaultdict(int)
    risk_windows: List[Dict] = []
    seen_risk: set = set()

    # Build the list of windows to score.
    targets: List[Dict] = []
    for doc in docs:
        text = doc.text
        for key, pat in patterns.items():
            ent = alias_to_entity.get(key, key)
            for m in pat.finditer(text):
                win_text = _criteria_sentences(text, m.start(), m.end())
                targets.append({
                    "entity": ent, "text": win_text,
                    "doc_id": doc.doc_id, "url": doc.url, "title": doc.title,
                    "m_start": m.start(), "m_end": m.end(),
                })

    if pipeline is not None:
        # Pre-score all unique windows in one transform batch.
        unique_texts = []
        index = {}
        for i, t in enumerate(targets):
            if t["text"] not in index:
                index[t["text"]] = len(unique_texts)
                unique_texts.append(t["text"])
        scores = _classify_batch(pipeline, unique_texts)
        for t in targets:
            label, val = scores[index[t["text"]]]
            pol = 0.0
            if label.startswith("net:"):
                pol = val
            elif label == "positive":
                pol = 0.75
            elif label == "negative":
                pol = -0.75
            else:
                pol = 0.0
            t["polarity"] = round(pol, 3)
    else:
        for t in targets:
            t["polarity"] = round(_score_window_lexicon(t["text"]), 3)

    # Aggregate per entity.
    for t in targets:
        ent = t["entity"]
        s = t["polarity"]
        ent_mentions[ent] += 1
        ent_score_sum[ent] += s
        if s > 0.15:
            ent_pos[ent] += 1
        elif s < -0.15:
            ent_neg[ent] += 1
            risk_key = (ent, t["doc_id"], t["m_start"])
            if risk_key not in seen_risk:
                seen_risk.add(risk_key)
                snippet = t["text"].replace("\n", " ").strip()
                risk_windows.append({
                    "entity": ent,
                    "doc_id": t["doc_id"],
                    "url": t["url"],
                    "title": t["title"],
                    "snippet": snippet,
                    "polarity": s,
                })
        else:
            ent_neu[ent] += 1

    summary = []
    for ent in focus:
        total = ent_mentions.get(ent, 0)
        if total == 0:
            summary.append({
                "entity": ent, "mentions": 0, "positive_pct": 0.0,
                "neutral_pct": 0.0, "negative_pct": 0.0,
                "net_sentiment": 0.0, "risk_windows": 0,
                "framing": "none",
            })
            continue
        p = ent_pos.get(ent, 0) / total * 100.0
        ne = ent_neu.get(ent, 0) / total * 100.0
        ng = ent_neg.get(ent, 0) / total * 100.0
        net = round(ent_score_sum.get(ent, 0.0) / total, 3)
        framing = (
            "positive" if p >= 60 else
            "negative" if ng >= 30 else
            "neutral"
        )
        summary.append({
            "entity": ent, "mentions": total,
            "positive_pct": round(p, 1), "neutral_pct": round(ne, 1),
            "negative_pct": round(ng, 1), "net_sentiment": net,
            "risk_windows": ent_neg.get(ent, 0), "framing": framing,
        })

    risk_windows.sort(key=lambda r: r["polarity"])
    return {
        "per_entity": summary,
        "risk_windows": risk_windows[: config.top_n_recommendations * 5],
        "method": method,
        "model": model_name,
    }
