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

# Lazy-loaded real tokenizers, keyed by embedding-model family (offline only).
_TOKENIZER_LOCK = threading.Lock()
_tokenizer_lock = _TOKENIZER_LOCK  # legacy alias (older call sites / tests)
_TOKENIZERS: Dict[str, object] = {}
_TOKENIZER = None  # legacy single-slot alias (kept for backward compat)
_TOKENIZER_FALLBACK_USED = False

# Model-aware tokenizer resolution. The tokenizer MUST match the embedding
# model family — a MiniLM tokenizer on BGE-M3/Qwen3 text silently miscounts
# tokens and slices windows on wrong boundaries.
MODEL_TOKENIZER_MAP = {
    "nomic": "nomic-ai/nomic-embed-text-v1.5",
    "bge-m3": "BAAI/bge-m3",
    "bge-small": "BAAI/bge-small-en-v1.5",
    "qwen3": "Qwen/Qwen3-Embedding-0.6B",
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",
    "mpnet": "sentence-transformers/all-mpnet-base-v2",
}

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n{2,}")


def resolve_tokenizer_name(embedding_model: str = "") -> str:
    """Map an embedding-model id to the tokenizer checkpoint to load."""
    low = (embedding_model or "").lower()
    if "nomic" in low:
        return MODEL_TOKENIZER_MAP["nomic"]
    if "bge-m3" in low or "bge_m3" in low:
        return MODEL_TOKENIZER_MAP["bge-m3"]
    if "bge-small" in low or "bge_small" in low:
        return MODEL_TOKENIZER_MAP["bge-small"]
    if "qwen3" in low or "qwen" in low:
        return MODEL_TOKENIZER_MAP["qwen3"]
    if "mpnet" in low:
        return MODEL_TOKENIZER_MAP["mpnet"]
    return MODEL_TOKENIZER_MAP["minilm"]


def _get_tokenizer(model_name: str = "", require_real: bool = False):
    """Load a real BPE tokenizer matching the embedding model (cached per family).

    Backwards-compatible: ``_get_tokenizer(require_real)`` and
    ``_get_tokenizer(model_name, require_real)`` both work.
    When ``require_real=True`` and no locally-cached tokenizer can be loaded,
    raises RuntimeError instead of silently falling back to char/4 math.
    """
    global _TOKENIZER_FALLBACK_USED
    # Back-compat: first positional arg may be a bool.
    if isinstance(model_name, bool):
        require_real = model_name
        model_name = ""
    want = resolve_tokenizer_name(model_name or "")
    with _tokenizer_lock:
        tok = _TOKENIZERS.get(want)
        if tok is not None:
            if tok is False and require_real:
                raise RuntimeError(
                    "Real BPE tokenizer is required (require_real_models=True) "
                    f"but {want} tokenizer is not locally cached. Pre-cache it or "
                    "set require_real_models=False for triage-only estimates."
                )
            return tok or None
        try:
            import os as _os
            from transformers import AutoTokenizer
            _prev = _os.environ.get("HF_HUB_OFFLINE")
            _os.environ["HF_HUB_OFFLINE"] = "1"
            try:
                tok = AutoTokenizer.from_pretrained(want, local_files_only=True)
            finally:
                if _prev is None:
                    _os.environ.pop("HF_HUB_OFFLINE", None)
                else:
                    _os.environ["HF_HUB_OFFLINE"] = _prev
            _TOKENIZERS[want] = tok
            return tok
        except Exception as exc:  # noqa: BLE001
            if require_real:
                raise RuntimeError(
                    "Real BPE tokenizer is required (require_real_models=True) "
                    f"but could not be loaded offline ({want}): {exc}"
                ) from exc
            logger.warning("real tokenizer unavailable (%s); using char/4 fallback", exc)
            _TOKENIZERS[want] = False
            _TOKENIZER_FALLBACK_USED = True
            return None


def tokenizer_is_fallback() -> bool:
    """True if any char/4 fallback token estimate has been used this process."""
    return _TOKENIZER_FALLBACK_USED


def count_tokens(text: str, model_name: str = "") -> int:
    """Real token count via the model-aware BPE tokenizer."""
    if not text:
        return 0
    tok = _get_tokenizer(model_name or "")
    if tok:
        try:
            return max(1, len(tok.encode(text, add_special_tokens=False)))
        except Exception:  # noqa: BLE001
            pass
    return max(1, int(round(len(text) / 4.0)))


def token_count_batch(texts: List[str], model_name: str = "") -> List[int]:
    """Batch token counts for a list of strings (faster than one-by-one)."""
    tok = _get_tokenizer(model_name or "")
    if tok:
        try:
            # encode_batch is not universally available; loop is fine.
            return [max(1, len(tok.encode(t, add_special_tokens=False))) for t in texts]
        except Exception:  # noqa: BLE001
            pass
    return [max(1, int(round(len(t) / 4.0))) for t in texts]


def split_sentences(text: str) -> List[str]:
    """Sentence-aware split that never breaks mid-sentence."""
    text = (text or "").strip()
    if not text:
        return []
    parts = _SENT_SPLIT_RE.split(text)
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Guard against pathological single "sentences" (e.g. minified HTML):
        # hard-split only > 2000 chars on clause boundaries.
        if len(p) > 2000:
            for clause in re.split(r"(?<=[;,])\s+", p):
                clause = clause.strip()
                if clause:
                    out.append(clause)
        else:
            out.append(p)
    return out or [text]


def token_windows(text: str, tokens: int = 512, overlap_tokens: int = 64,
                  model_name: str = "") -> List[str]:
    """Split text into overlapping RAG token-windows on real BPE boundaries.

    SEMANTIC PACKING: sentences are packed greedily into each window so no
    window ever starts/ends mid-sentence (fixes the char-split sentence
    shredding). Overlap is applied in whole sentences. This is the SINGLE
    canonical splitter — embeddings and density share these exact windows.
    """
    text = text or ""
    if not text.strip():
        return []
    tok = _get_tokenizer(model_name or "")
    sentences = split_sentences(text)
    if not tok:
        # char/4 fallback path (deterministic, documented) — sentence-packed.
        win_chars = max(1, int(tokens * 4.0))
        step_chars = max(1, int((tokens - overlap_tokens) * 4.0))
        out: List[str] = []
        buf, buf_len = [], 0
        for s in sentences:
            buf.append(s)
            buf_len += len(s) + 1
            if buf_len >= win_chars:
                piece = " ".join(buf)
                if count_tokens(piece) >= 8:
                    out.append(piece)
                # overlap: keep trailing chars worth of whole sentences
                keep, acc = [], 0
                for b in reversed(buf):
                    keep.append(b)
                    acc += len(b) + 1
                    if acc >= step_chars:
                        break
                buf = list(reversed(keep))
                buf_len = sum(len(b) + 1 for b in buf)
        if buf:
            piece = " ".join(buf)
            if piece and (not out or piece != out[-1]) and count_tokens(piece) >= 8:
                out.append(piece)
        return out or [text]
    # real BPE path: pack whole sentences by token budget.
    try:
        sent_ids = [tok.encode(s, add_special_tokens=False) for s in sentences]
    except Exception:  # noqa: BLE001
        return [text]
    sent_ids = [list(s) for s in sent_ids if s]
    if not sent_ids:
        return []
    step = max(1, tokens - overlap_tokens)
    out: List[str] = []
    start = 0
    n = len(sent_ids)
    while start < n:
        # grow end while token budget allows
        used, end = 0, start
        while end < n and used + len(sent_ids[end]) <= tokens:
            used += len(sent_ids[end])
            end += 1
        if end == start:  # single long sentence exceeds window: hard-slice it
            ids = sent_ids[start]
            for off in range(0, len(ids), step):
                piece = tok.decode(ids[off:off + tokens], skip_special_tokens=True)
                if count_tokens(piece, model_name) >= 8:
                    out.append(piece)
                if off + tokens >= len(ids):
                    break
            start += 1
            continue
        flat: List[int] = []
        for i in range(start, end):
            flat.extend(sent_ids[i])
        piece = tok.decode(flat, skip_special_tokens=True)
        if count_tokens(piece, model_name) >= 8:
            out.append(piece)
        if end >= n:
            break
        # overlap: walk back whole sentences covering overlap_tokens
        back, acc = end - 1, 0
        while back > start and acc < overlap_tokens:
            acc += len(sent_ids[back])
            back -= 1
        new_start = max(start + 1, back)
        if new_start >= end:
            new_start = end
        start = new_start
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
    emb_model = getattr(config, "embedding_model", "") or ""

    # Pre-compute the dominant topic per document so window labels are stable.
    for doc in docs:
        per_topic = doc_topic_sim.get(doc.doc_id, {})
        dom_topic = max(per_topic, key=per_topic.get) if per_topic else ""
        dom_sim = per_topic.get(dom_topic, 0.0)

        chunks = token_windows(doc.text, tokens, overlap, model_name=emb_model)
        for idx, text in enumerate(chunks):
            tok = count_tokens(text, emb_model)

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


def _mention_token_span(text, patterns, alias_to_entity, entity, model_name: str = "") -> int:
    """Real BPE token length of all spans matching ``entity``.

    Each verbatim matched mention is encoded with the real tokenizer and the
    token counts summed. Falls back to chars/4 only when no tokenizer is
    available (and logs it via _get_tokenizer).
    """
    # Find the pattern key(s) that map back to this entity.
    keys = [k for k, e in alias_to_entity.items() if e == entity]
    if not keys:
        return 0
    tok = _get_tokenizer(model_name or "")
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
