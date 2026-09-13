"""Shared analysis context.

This module performs the heavy, once-only computation that every downstream
analysis reuses:

* chunking + embedding of every document
* embedding of target topics
* per-entity mention counts and entity "centroid" vectors (the average
  embedding of corpus chunks that actually mention the entity)
* per-document / per-topic relevance (max chunk similarity to each topic)
* entity co-occurrence graph construction

The result is an :class:`AnalysisContext` consumed by the proximity, citation
gap, invisibility and recommendation analyzers.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import numpy as np

from ..harvester.base import Document
from ..nlp.embedder import Embedder
from ..nlp.ner import NER
from ..nlp.cooccurrence import CoOccurrenceGraph
from ..utils import chunk_text, get_logger

logger = get_logger("ragevda.analysis.context")


@dataclass
class EntityStats:
    name: str
    docs_mentioned: int = 0
    total_mentions: int = 0
    centroid: Optional[np.ndarray] = None
    name_vec: Optional[np.ndarray] = None
    topic_proximity: Dict[str, float] = field(default_factory=dict)
    topic_doc_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class AnalysisContext:
    config: object
    docs: List[Document]
    topic_vecs: Dict[str, np.ndarray] = field(default_factory=dict)
    doc_topic_max_sim: Dict[str, Dict[str, float]] = field(default_factory=dict)
    entity_stats: Dict[str, EntityStats] = field(default_factory=dict)
    entity_docs: Dict[str, Set[str]] = field(default_factory=dict)
    doc_chunk_vecs: Dict[str, List[np.ndarray]] = field(default_factory=dict)
    doc_by_id: Dict[str, object] = field(default_factory=dict)
    topic_thresholds: Dict[str, float] = field(default_factory=dict)
    cooccur: CoOccurrenceGraph = None  # type: ignore
    embedding_kind: str = ""
    ner_kind: str = ""
    embedding_model: str = ""
    ner_model: str = ""


def build_context(config, docs: List[Document], embedder: Embedder,
                  ner: NER, cooccur: CoOccurrenceGraph) -> AnalysisContext:
    logger.info("building analysis context for %d documents", len(docs))

    # 1. Chunk + embed every document (UNIFIED semantic windows) ---------
    # Single chunking pass shared by embeddings AND density: chunk_text() now
    # delegates to the same sentence-aware BPE packer as token_windows(), so
    # proximity and density measure IDENTICAL windows (double-chunking fix).
    all_chunks: List[str] = []
    chunk_owner: List[str] = []  # doc_id per chunk
    doc_chunks: Dict[str, List[str]] = {}
    doc_chunk_vecs: Dict[str, List[np.ndarray]] = {}

    for doc in docs:
        chunks = chunk_text(doc.text, max_chars=config.sentence_chunk_chars)
        if not chunks:
            continue
        doc_chunks[doc.doc_id] = chunks
        for ch in chunks:
            all_chunks.append(ch)
            chunk_owner.append(doc.doc_id)
        doc_chunk_vecs[doc.doc_id] = []

    ctx = AnalysisContext(
        config=config, docs=docs, cooccur=cooccur,
        embedding_kind=embedder.kind(), ner_kind=ner.kind(),
        embedding_model=getattr(embedder, "used_model", "") or config.embedding_model,
        ner_model=getattr(ner, "used_model", "") or config.spacy_model,
    )
    if not all_chunks:
        logger.warning("no chunks to embed; corpus may be empty")
        return ctx

    logger.info("embedding %d chunks", len(all_chunks))
    # Encode in bounded batches and log real progress so the web UI's bar
    # moves during this CPU-heavy phase (single-shot encode is silent and can
    # look stuck for many minutes on a large corpus).
    chunk_vecs: List[np.ndarray] = []
    EMBED_BATCH = 64
    total_chunks = len(all_chunks)
    for start in range(0, total_chunks, EMBED_BATCH):
        sl = all_chunks[start:start + EMBED_BATCH]
        chunk_vecs.extend(embedder.encode(sl, show_progress=False))
        done = min(start + len(sl), total_chunks)
        if done % (EMBED_BATCH * 4) == 0 or done == total_chunks:
            logger.info("embedded %d/%d chunks", done, total_chunks)
    # assign back
    by_owner: Dict[str, List[np.ndarray]] = defaultdict(list)
    for ch_vec, owner in zip(chunk_vecs, chunk_owner):
        by_owner[owner].append(ch_vec)
    doc_chunk_vecs = by_owner

    # 2. Embed topics -------------------------------------------------
    for topic in config.industry_topics:
        ctx.topic_vecs[topic] = embedder.encode([topic])[0]

    # 3. Mention patterns for brand + competitors --------------------
    focus = config.all_entities()
    patterns, alias_to_entity = NER.build_mention_patterns(
        focus, config.entity_alias_map())

    entity_chunks: Dict[str, List[str]] = defaultdict(list)
    entity_doc_set: Dict[str, Set[str]] = defaultdict(set)
    entity_total: Counter = Counter()
    entity_doc_count: Counter = Counter()

    # 4. Co-occurrence + mention scanning per document ---------------
    # NER patterns built ONCE and reused (no per-doc rebuild); chunk lists
    # reused from the single chunking pass above (no re-chunk).
    for doc in docs:
        chunks = doc_chunks.get(doc.doc_id) or []
        # count mentions across whole doc text
        counts = NER.find_mentions(doc.text, patterns, alias_to_entity)
        for ent_low, c in counts.items():
            if c <= 0:
                continue
            orig = next((e for e in focus if e.lower() == ent_low), ent_low)
            entity_total[orig] += c
            entity_doc_count[orig] += 1
            entity_doc_set[orig].add(doc.doc_id)
            # collect chunks mentioning this entity for centroid
            for ch in chunks:
                if ent_low in ch.lower():
                    entity_chunks[orig].append(ch)
        # co-occurrence graph (only real brand/competitor names as nodes)
        cooccur.add_document(doc.doc_id, doc.text, focus_entities=focus)

    # 5. Entity centroids + name vectors -----------------------------
    for ent in focus:
        stats = EntityStats(name=ent)
        stats.docs_mentioned = entity_doc_count.get(ent, 0)
        stats.total_mentions = entity_total.get(ent, 0)
        stats.name_vec = embedder.encode([ent])[0]
        chunks = entity_chunks.get(ent, [])
        if chunks:
            vecs = embedder.encode(chunks)
            stats.centroid = np.mean(vecs, axis=0)
        else:
            # fall back to name-only vector when never mentioned in corpus
            stats.centroid = stats.name_vec
        ctx.entity_stats[ent] = stats
        ctx.entity_docs[ent] = entity_doc_set.get(ent, set())

    # 6. Per-document / per-topic max similarity ---------------------
    # Single vector-index per topic query is O(N) via matrix multiply on the
    # stacked chunk matrix (no per-doc Python O(N²) loop; FAISS-ready).
    for doc in docs:
        vecs = doc_chunk_vecs.get(doc.doc_id, [])
        per_topic: Dict[str, float] = {}
        if vecs:
            mat = np.stack(vecs, axis=0)  # (n, dim) — one stack per doc, reused
            for topic, tvec in ctx.topic_vecs.items():
                sims = mat @ tvec  # cosine (embeddings normalized)
                per_topic[topic] = float(np.max(sims))
        ctx.doc_topic_max_sim[doc.doc_id] = per_topic
    # Global ANN index over ALL chunks (FAISS when installed) for hybrid
    # retrieval / top-k diagnostics without O(N²) scans.
    try:
        from ..nlp.vector_index import VectorIndex
        if chunk_vecs:
            dim = int(np.asarray(chunk_vecs[0]).shape[0])
            _vidx = VectorIndex(dim)
            _vidx.add([f"{o}#{i}" for i, o in enumerate(chunk_owner)],
                      np.stack(chunk_vecs, axis=0))
            ctx.vector_index = _vidx  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    # 7. Topic proximity + topic-doc counts per entity ---------------
    ctx.doc_chunk_vecs = doc_chunk_vecs
    ctx.doc_by_id = {d.doc_id: d for d in docs}

    # 7b. Per-topic calibrated high-relevance threshold.
    # A fixed 0.70 is rarely met by short topic phrases under MiniLM, which
    # makes per-topic invisibility / share-of-voice come out empty. We instead
    # derive the threshold from the ACTUAL similarity distribution of the
    # harvested corpus (80th percentile, clamped to a sane band), so the
    # metric reflects real signal in the data rather than an arbitrary cut.
    ctx.topic_thresholds = {}
    for topic in ctx.topic_vecs:
        sims = [ctx.doc_topic_max_sim.get(d.doc_id, {}).get(topic, 0.0) for d in docs]
        sims = [s for s in sims if s > 0.0]
        if config.auto_threshold and sims:
            arr = np.array(sims, dtype=np.float32)
            p80 = float(np.percentile(arr, 80))
            thr = min(max(p80, 0.35), 0.85)
        else:
            thr = float(config.high_relevance_threshold)
        ctx.topic_thresholds[topic] = round(thr, 4)
    logger.info("calibrated topic thresholds: %s", ctx.topic_thresholds)

    for ent, stats in ctx.entity_stats.items():
        for topic, tvec in ctx.topic_vecs.items():
            prox = float(np.dot(stats.centroid, tvec))  # both normalized
            stats.topic_proximity[topic] = round(max(0.0, prox), 4)
            # docs highly relevant to topic AND mentioning entity
            cnt = 0
            for doc_id in ctx.entity_docs.get(ent, set()):
                sim = ctx.doc_topic_max_sim.get(doc_id, {}).get(topic, 0.0)
                if sim >= ctx.topic_thresholds.get(topic, config.high_relevance_threshold):
                    cnt += 1
            stats.topic_doc_counts[topic] = cnt

    logger.info("context built: %d entities, %d topics",
                len(ctx.entity_stats), len(ctx.topic_vecs))
    return ctx
