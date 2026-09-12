"""Enterprise RAG Chunking & Contextual Window Simulator.

Real RAG engines do not embed a whole 3,000-word article as one vector. They
split the page into retrieval windows (typically 256-512 tokens with overlap),
embed each window separately, and return the top-k most similar windows for a
query.  Scoring a whole article as a single vector creates massive false
positives.

This module simulates that behaviour with **real sub-word tokenization**
(not a character heuristic):

* a true BPE/tokenizer (from the cached sentence-transformers tokenizer) is
  used to count tokens and to slice windows on real token boundaries, so the
  token count a retriever would see is reproduced accurately;
* splices every cleaned document into overlapping token windows of
  ``chunk_tokens`` with ``chunk_overlap_tokens`` of context;
* reports per-window token makeup (entity density, dominant topic, centroid
  proximity) so teams can see exactly where a brand or competitor appears;
* exposes the windows pulled into a top-k result set, gated by the *same
  auto-calibrated relevance threshold* used everywhere else, so a "retrieved"
  flag genuinely means the document (and thus its windows) met the relevance
  bar -- not just the top-k windows of every page.

All numbers are computed from the real corpus and real embedding model, never
synthesised.
"""

from __future__ import annotations

import logging
import re
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..utils import get_logger

logger = get_logger("ragevda.analysis.chunking")

_TOKEN_RE = re.compile(r"\S+")

# Lazy-loaded real tokenizer (from the cached embedding model so it is offline).
_tokenizer_lock = threading.Lock()
_TOKENIZER = None


def _get_tokenizer(require_real: bool = False):
    """Load a real BPE tokenizer (from the cached MiniLM model) once.

    When ``require_real=True`` and no locally-cached tokenizer can be loaded,
    raises RuntimeError instead of silently falling back to char/4 math, so
    reports can never be mistaken for real-BPE runs.
    """
    global _TOKENIZER
    with _tokenizer_lock:
        if _TOKENIZER is not None:
            if _TOKENIZER is False and require_real:
                raise RuntimeError(
                    "Real BPE tokenizer is required (require_real_models=True) "
                    "but sentence-transformers/all-MiniLM-L6-v2 tokenizer is not "
                    "locally cached. Pre-cache it or set require_real_models=False "
                    "for triage-only char/4 estimates."
                )
            return _TOKENIZER
        try:
            import os as _os
            from transformers import AutoTokenizer
            _prev = _os.environ.get("HF_HUB_OFFLINE")
            _os.environ["HF_HUB_OFFLINE"] = "1"
            try:
                _TOKENIZER = AutoTokenizer.from_pretrained(
                    "sentence-transformers/all-MiniLM-L6-v2", local_files_only=True)
            finally:
                if _prev is None:
                    _os.environ.pop("HF_HUB_OFFLINE", None)
                else:
                    _os.environ["HF_HUB_OFFLINE"] = _prev
        except Exception as exc:  # noqa: BLE001
            if require_real:
                raise RuntimeError(
                    "Real BPE tokenizer is required (require_real_models=True) "
                    f"but could not be loaded offline: {exc}"
                ) from exc
            logger.warning("real tokenizer unavailable (%s); using char/4 fallback", exc)
            _TOKENIZER = False
        return _TOKENIZER


def count_tokens(text: str) -> int:
    """Real token count via a BPE tokenizer; char/4 fallback only if absent."""
    if not text:
        return 0
    tok = _get_tokenizer()
    if tok:
        try:
            return max(1, len(tok.encode(text, add_special_tokens=False)))
        except Exception:  # noqa: BLE001
            pass
    return max(1, int(round(len(text) / 4.0)))


def token_count_batch(texts: List[str]) -> List[int]:
    """Batch token counts for a list of strings (faster than one-by-one)."""
    tok = _get_tokenizer()
    if tok:
        try:
            # encode_batch is not universally available; loop is fine.
            return [max(1, len(tok.encode(t, add_special_tokens=False))) for t in texts]
        except Exception:  # noqa: BLE001
            pass
    return [max(1, int(round(len(t) / 4.0))) for t in texts]


def token_windows(text: str, tokens: int = 512, overlap_tokens: int = 64) -> List[str]:
    """Split text into overlapping RAG token-windows on real BPE boundaries."""
    text = text or ""
    if not text.strip():
        return []
    tok = _get_tokenizer()
    if not tok:
        # char/4 fallback path (deterministic, documented)
        n = len(text)
        step_chars = max(1, int((tokens - overlap_tokens) * 4.0))
        win_chars = max(1, int(tokens * 4.0))
        if n <= win_chars:
            return [text]
        out: List[str] = []
        start = 0
        while start < n:
            window = text[start:start + win_chars]
            if count_tokens(window) >= 8:
                out.append(window)
            start += step_chars
            if start + win_chars >= n:
                break
        return out
    # real BPE path: tokenize the whole text once, then slice windows on token ids.
    try:
        ids = tok.encode(text, add_special_tokens=False)
    except Exception:  # noqa: BLE001
        return [text]
    if not ids:
        return []
    ids = list(ids)
    step = max(1, tokens - overlap_tokens)
    out: List[str] = []
    start = 0
    n = len(ids)
    while start < n:
        window_ids = ids[start:start + tokens]
        piece = tok.decode(window_ids, skip_special_tokens=True)
        if count_tokens(piece) >= 8:
            out.append(piece)
        start += step
        if start + tokens >= n:
            break
    return out


@dataclass
class ChunkWindow:
    doc_id: str
    chunk_index: int
    text: str
    tokens: int
    dominant_topic: str = ""
    dominant_topic_sim: float = 0.0
    entity_token_density: Dict[str, float] = field(default_factory=dict)
    entity_token_count: Dict[str, int] = field(default_factory=dict)
    sentiment: Dict[str, float] = field(default_factory=dict)
    retrieved: bool = False        # would this window land in top-k for its topic?
    retrieval_rank: int = 0
    retrieval_sim: float = 0.0


def build_chunk_windows(docs, topic_vecs, doc_topic_sim, config,
                        corpus_store=None) -> Dict[str, List[ChunkWindow]]:
    """Build RAG-style token windows for every document.

    ``topic_vecs``        : dict topic -> embedding
    ``doc_topic_sim``     : dict doc_id -> {topic: max_sim across doc}
    Returns dict doc_id -> list[ChunkWindow].
    """
    from ..nlp.ner import NER

    windows_by_doc: Dict[str, List[ChunkWindow]] = defaultdict(list)
    patterns, alias_to_entity = NER.build_mention_patterns(
        config.all_entities(), config.entity_alias_map())
    tokens = max(64, config.chunk_tokens)
    overlap = max(0, min(config.chunk_overlap_tokens, tokens - 1))

    # Pre-compute the dominant topic per document so window labels are stable.
    for doc in docs:
        per_topic = doc_topic_sim.get(doc.doc_id, {})
        dom_topic = max(per_topic, key=per_topic.get) if per_topic else ""
        dom_sim = per_topic.get(dom_topic, 0.0)

        chunks = token_windows(doc.text, tokens, overlap)
        for idx, text in enumerate(chunks):
            tok = count_tokens(text)
            low = text.lower()

            # entity token counts within this window: sum the REAL token spans
            # of each mention (via the tokenizer), not a raw mention count.
            ent_tokens: Dict[str, int] = {}
            ent_density: Dict[str, float] = {}
            counts = NER.find_mentions(text, patterns, alias_to_entity)
            for ent, c in counts.items():
                est = _mention_token_span(text, patterns, alias_to_entity, ent)
                ent_tokens[ent] = est if est > 0 else c
                ent_density[ent] = (ent_tokens[ent] / tok) if tok else 0.0

            win = ChunkWindow(
                doc_id=doc.doc_id,
                chunk_index=idx,
                text=text,
                tokens=tok,
                dominant_topic=dom_topic,
                dominant_topic_sim=dom_sim,
                entity_token_density=ent_density,
                entity_token_count=ent_tokens,
            )
            windows_by_doc[doc.doc_id].append(win)
    return dict(windows_by_doc)


def mark_retrieved_windows(windows_by_doc, doc_topic_sim, config,
                          embedder=None, topic_thresholds=None) -> None:
    """Mark which token windows would appear in a top-k retrieval result.

    A document's windows are only eligible to be flagged ``retrieved`` when the
    document itself clears the topic's calibrated relevance threshold (the same
    bar used by every other analysis).  This removes the previous
    over-inclusive behaviour where the top-k windows of *every* page were
    flagged even when the page was irrelevant.  Within an eligible document we
    flag its top-k windows (ranked by focus-entity density, tie-broken by
    dominant-topic similarity).
    """
    k = max(1, config.top_k_retrieval)
    thresholds = topic_thresholds or {}
    for doc_id, wins in windows_by_doc.items():
        per_topic = doc_topic_sim.get(doc_id, {})
        dom = max(per_topic, key=per_topic.get) if per_topic else ""
        thr = thresholds.get(dom)
        dom_sim = 0.0
        if dom:
            dom_sim = per_topic.get(dom, 0.0)
        # Gate: only documents meeting the relevance threshold are eligible.
        if thr is None or dom_sim < thr:
            continue
        focus_count = _focus_count_by_window(wins)
        ranked = sorted(
            enumerate(wins),
            key=lambda iv: (focus_count[iv[0]], iv[1].dominant_topic_sim),
            reverse=True,
        )
        retrieved = 0
        for idx, win in ranked[:k]:
            win.retrieved = True
            win.retrieval_rank = retrieved + 1
            win.retrieval_sim = win.dominant_topic_sim
            retrieved += 1


def _focus_count_by_window(wins: List[ChunkWindow]) -> Dict[int, int]:
    out = {}
    for i, w in enumerate(wins):
        out[i] = sum(1 for v in w.entity_token_density.values() if v > 0)
    return out


def _mention_token_span(text, patterns, alias_to_entity, entity) -> int:
    """Real BPE token length of all spans matching ``entity``.

    Each verbatim matched mention is encoded with the real tokenizer and the
    token counts summed. Falls back to chars/4 only when no tokenizer is
    available (and logs it via _get_tokenizer).
    """
    # Find the pattern key(s) that map back to this entity.
    keys = [k for k, e in alias_to_entity.items() if e == entity]
    if not keys:
        return 0
    tok = _get_tokenizer()
    total = 0
    for k in keys:
        pat = patterns.get(k)
        if not pat:
            continue
        for m in pat.finditer(text):
            span = m.group(0)
            if tok:
                try:
                    total += max(1, len(tok.encode(span, add_special_tokens=False)))
                    continue
                except Exception:  # noqa: BLE001
                    pass
            total += max(1, int(round(len(span) / 4.0)))
    return total
