"""ANN vector index (FAISS when available, brute-force otherwise).

Replaces O(N²) scans and per-doc ``np.stack`` with a single indexed search.
API is deliberately tiny so call sites stay readable:

    idx = VectorIndex(dim)
    idx.add(ids, vecs)          # vecs: (N, dim) L2-normalized
    scores, ids = idx.search(query_vec, top_k=5)

FAISS ``faiss-cpu`` is optional: if import fails we use a NumPy brute-force
index with identical semantics (cosine via inner product on normalized vecs).
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np


class VectorIndex:
    def __init__(self, dim: int) -> None:
        self.dim = int(dim)
        self._ids: List[str] = []
        self._mat: List[np.ndarray] = []
        self._faiss = None
        try:
            import faiss  # type: ignore
            self._faiss = faiss.IndexFlatIP(self.dim)
        except Exception:  # noqa: BLE001
            self._faiss = None

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, ids: Sequence[str], vecs: np.ndarray) -> None:
        vecs = np.asarray(vecs, dtype=np.float32)
        if vecs.ndim == 1:
            vecs = vecs.reshape(1, -1)
        # L2-normalize defensively (cosine == inner product).
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = vecs / norms
        self._ids.extend(list(ids))
        self._mat.append(vecs)
        if self._faiss is not None:
            try:
                self._faiss.add(vecs)
            except Exception:  # noqa: BLE001
                self._faiss = None

    def _brute(self, q: np.ndarray, top_k: int):
        if not self._mat:
            return [], []
        mat = np.vstack(self._mat)
        sims = mat @ q
        k = min(top_k, len(sims))
        idx = np.argpartition(-sims, k - 1)[:k]
        idx = idx[np.argsort(-sims[idx])]
        return [float(sims[i]) for i in idx], [self._ids[i] for i in idx]

    def search(self, query_vec: np.ndarray, top_k: int = 5) -> Tuple[List[float], List[str]]:
        q = np.asarray(query_vec, dtype=np.float32).ravel()
        n = np.linalg.norm(q)
        if n:
            q = q / n
        if self._faiss is not None:
            try:
                import numpy as _np
                D, idx_arr = self._faiss.search(_np.ascontiguousarray(q.reshape(1, -1)), min(top_k, len(self._ids)))
                out_s, out_i = [], []
                for s, j in zip(D[0], idx_arr[0]):
                    if int(j) < 0:
                        continue
                    out_s.append(float(s))
                    out_i.append(self._ids[int(j)])
                return out_s, out_i
            except Exception:  # noqa: BLE001
                pass
        return self._brute(q, top_k)
