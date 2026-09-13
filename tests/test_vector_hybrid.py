"""Vector index + hybrid BM25 + embed cache (no models, no network)."""
import numpy as np

from ragevda.nlp.vector_index import VectorIndex
from ragevda.nlp.hybrid import BM25, reciprocal_rank_fusion, Reranker


def _normed(n, d, seed=0):
    rng = np.random.RandomState(seed)
    m = rng.rand(n, d).astype(np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    return m


def test_vector_index_topk_exact():
    idx = VectorIndex(8)
    vecs = _normed(10, 8)
    idx.add([f"d{i}" for i in range(10)], vecs)
    sims, ids = idx.search(vecs[3], top_k=3)
    assert ids[0] == "d3"
    assert sims[0] > 0.99


def test_bm25_exact_term_wins():
    docs = ["apple banana orange", "quantum flux capacitor manual", "apple pie recipe"]
    scores = BM25(docs).score("quantum flux capacitor")
    assert scores[1] == max(scores) and scores[1] > 0


def test_rrf_fusion_monotone():
    fused = reciprocal_rank_fusion([0.9, 0.1], [0.1, 0.9])
    assert len(fused) == 2 and all(f > 0 for f in fused)


def test_reranker_fail_open_without_cache():
    r = Reranker()
    out = r.rerank("q", ["a", "b"], top_k=2)
    assert len(out) == 2  # zeros when model absent, never raises


def test_embed_cache_key_stable():
    from ragevda.nlp.embedder import _EmbedCache
    assert _EmbedCache.key("m", "hello") == _EmbedCache.key("m", "hello")
    assert _EmbedCache.key("m1", "hello") != _EmbedCache.key("m2", "hello")
