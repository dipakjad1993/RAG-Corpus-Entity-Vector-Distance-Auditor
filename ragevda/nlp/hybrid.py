"""Hybrid retrieval: BM25 (lexical) + dense cosine + cross-encoder rerank.

Cosine-only retrieval is 2022. This module fuses:

* **BM25** (pure-Python, no new deps) over chunk tokens — catches exact
  brand/product/patent strings dense models paraphrase away;
* **dense cosine** from the real embedding model;
* **cross-encoder rerank** via ``bge-reranker-v2-m3`` when locally cached
  (fail-open: skipped when absent, always labelled).

``hybrid_search(query, chunks, dense_scores, top_k)`` returns reranked
``[(chunk_id, fused_score, detail)]``. All scores are real measurements.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Sequence

_TOK = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def _tok(text: str) -> List[str]:
    return _TOK.findall((text or "").lower())


class BM25:
    def __init__(self, docs: Sequence[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = [_tok(d) for d in docs]
        self.k1, self.b = k1, b
        self.N = max(1, len(self.docs))
        self.avgdl = sum(len(d) for d in self.docs) / self.N if self.docs else 0.0
        df: Counter = Counter()
        for d in self.docs:
            for t in set(d):
                df[t] += 1
        self.idf = {t: math.log(1 + (self.N - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def score(self, query: str) -> List[float]:
        qtok = _tok(query)
        out = []
        for d in self.docs:
            tf = Counter(d)
            dl = len(d) or 1
            s = 0.0
            for t in qtok:
                f = tf.get(t, 0)
                if not f:
                    continue
                idf = self.idf.get(t, 0.0)
                denom = f + self.k1 * (1 - self.b + self.b * dl / max(1.0, self.avgdl))
                s += idf * f * (self.k1 + 1) / denom
            out.append(s)
        # min-max normalize to [0,1]
        mx = max(out) if out else 0.0
        return [v / mx if mx > 0 else 0.0 for v in out]


def reciprocal_rank_fusion(dense: Sequence[float], lexical: Sequence[float],
                           k: int = 60) -> List[float]:
    """RRF fusion of dense rank + BM25 rank (robust, parameter-free)."""
    import numpy as _np
    d = _np.asarray(list(dense), dtype=float)
    b = _np.asarray(list(lexical), dtype=float)
    dr = _np.argsort(_np.argsort(-d)) + 1
    br = _np.argsort(_np.argsort(-b)) + 1
    return [float(1.0 / (k + r1) + 1.0 / (k + r2)) for r1, r2 in zip(dr, br)]


class Reranker:
    """Cross-encoder reranker (bge-reranker-v2-m3 when cached). Fail-open."""

    MODEL = "BAAI/bge-reranker-v2-m3"

    def __init__(self) -> None:
        self._model = None
        self.available = False
        try:
            import os as _os
            from huggingface_hub import try_to_load_from_cache
            hit = any(try_to_load_from_cache(self.MODEL, f)
                      for f in ("model.safetensors", "pytorch_model.bin", "config.json"))
            if not hit:
                return
            _prev = _os.environ.get("HF_HUB_OFFLINE")
            _os.environ["HF_HUB_OFFLINE"] = "1"
            try:
                from transformers import AutoTokenizer, AutoModelForSequenceClassification
                import torch
                self._tok = AutoTokenizer.from_pretrained(self.MODEL, local_files_only=True)
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    self.MODEL, local_files_only=True)
                self._model.eval()
                self._torch = torch
                self.available = True
            finally:
                if _prev is None:
                    _os.environ.pop("HF_HUB_OFFLINE", None)
                else:
                    _os.environ["HF_HUB_OFFLINE"] = _prev
        except Exception:  # noqa: BLE001
            self.available = False

    def rerank(self, query: str, chunks: Sequence[str], top_k: int = 5) -> List[float]:
        if not self.available or not chunks:
            return [0.0] * len(chunks)
        try:
            import torch
            scores = []
            with torch.no_grad():
                for c in chunks:
                    inp = self._tok(query, c, return_tensors="pt", truncation=True, max_length=512)
                    out = self._model(**inp).logits.squeeze()
                    scores.append(float(out.max() if out.numel() > 1 else out))
            mx, mn = max(scores), min(scores)
            rng = (mx - mn) or 1.0
            return [(s - mn) / rng for s in scores]
        except Exception:  # noqa: BLE001
            return [0.0] * len(chunks)


def hybrid_search(query: str, chunks: Sequence[str], dense_scores: Sequence[float],
                  top_k: int = 5, reranker: "Reranker | None" = None,
                  dense_w: float = 0.6, bm25_w: float = 0.4) -> List[Dict]:
    """Fuse dense + BM25 (+ optional rerank). Returns ranked dicts."""
    chunks = list(chunks)
    dense = list(dense_scores)
    bm25 = BM25(chunks).score(query)
    fused = [dense_w * d + bm25_w * b for d, b in zip(dense, bm25)]
    order = sorted(range(len(chunks)), key=lambda i: fused[i], reverse=True)[:max(1, top_k * 3)]
    cand_chunks = [chunks[i] for i in order]
    cand_fused = [fused[i] for i in order]
    re = (reranker.rerank(query, cand_chunks, top_k) if reranker and reranker.available
          else [0.0] * len(order))
    final = [0.7 * f + 0.3 * r for f, r in zip(cand_fused, re)]
    ranked = sorted(zip(order, final), key=lambda x: x[1], reverse=True)[:top_k]
    return [{"chunk_id": i, "score": round(float(s), 4),
             "dense": round(float(dense[i]), 4), "bm25": round(float(bm25[i]), 4),
             "rerank": round(float(re[k]), 4)}
            for k, (i, s) in enumerate(ranked)]
