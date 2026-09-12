"""Local vector embedding & semantic mapping.

Primary engine: Hugging Face ``sentence-transformers`` running fully locally
(e.g. ``all-MiniLM-L6-v2`` or ``bge-small-en-v1.5``).  All computation stays
on the operator's machine -- no OpenAI / paid API calls.

There is NO synthetic fallback in the default path: when
``require_real=True`` (the orchestrator default) and no locally-cached real
checkpoint can be loaded, initialisation raises ``RuntimeError`` instead of
emitting degraded vectors. A hashing-vectorizer triage path exists only for
explicit opt-in (``use_fallback=True`` or ``require_real=False``) and is always
reported as ``tfidf-fallback`` in ``kind()`` and the run's ``data_integrity``.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional

import numpy as np

from ..utils import get_logger

logger = get_logger("ragevda.nlp.embedder")


class Embedder:
    # Ordered real-model fallback chain. Each model must be verified present in
    # the local HF cache before use, so we never touch the network at audit time
    # and never degrade to a synthetic embedder when the operator asked for real
    # models. We prefer the operator's requested model first, then fall back to
    # smaller equally-real cached sentence-transformers checkpoints.
    FALLBACK_CHAIN = [
        "BAAI/bge-small-en-v1.5",
        "sentence-transformers/all-mpnet-base-v2",
        "sentence-transformers/all-MiniLM-L6-v2",
    ]

    def __init__(self, model_name: str, use_fallback: bool = False,
                 require_real: bool = False) -> None:
        self.model_name = model_name
        self._model = None
        self._vec = None  # fallback vectorizer
        self.used_model = None  # exact checkpoint actually loaded (for auditing)
        self._kind = "sentence-transformers"
        if use_fallback:
            self._init_fallback()
            return
        self._init_transformers(require_real=require_real)

    # ------------------------------------------------------------------
    def _locally_cached(self, model_name: str) -> bool:
        """Return True when a model snapshot is already in the local HF cache
        (i.e. can be loaded without any network round-trip)."""
        try:
            from huggingface_hub import try_to_load_from_cache

            candidates = ["model.safetensors", "pytorch_model.bin", "modules.json"]
            return any(
                try_to_load_from_cache(model_name, fname) for fname in candidates
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("cache probe failed for %s: %s", model_name, exc)
            return False

    def _init_transformers(self, require_real: bool = False) -> None:
        import os as _os
        from sentence_transformers import SentenceTransformer

        candidates = [self.model_name] + [
            m for m in self.FALLBACK_CHAIN if m != self.model_name
        ]

        # Load strictly from the local cache (the models were verified cached)
        # so a transient network failure or missing/gated HF repo can never
        # abort the audit mid-run.
        _prev_offline = _os.environ.get("HF_HUB_OFFLINE")
        _prev_endpoint = _os.environ.get("HF_ENDPOINT")
        _os.environ["HF_HUB_OFFLINE"] = "1"
        try:
            return self._try_cached_transformers(
                SentenceTransformer, candidates, require_real)
        finally:
            if _prev_offline is None:
                _os.environ.pop("HF_HUB_OFFLINE", None)
            else:
                _os.environ["HF_HUB_OFFLINE"] = _prev_offline
            if _prev_endpoint is None:
                _os.environ.pop("HF_ENDPOINT", None)
            else:
                _os.environ["HF_ENDPOINT"] = _prev_endpoint

    def _try_cached_transformers(self, SentenceTransformer, candidates,
                                 require_real: bool) -> None:
        for cand in candidates:
            if not self._locally_cached(cand):
                logger.info("embedding model %s not in local cache; skip", cand)
                continue
            try:
                logger.info("loading embedding model %s", cand)
                self._model = SentenceTransformer(cand)
                self.used_model = cand
                self._kind = "sentence-transformers"
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "cached embedding model %s failed to load (%s); trying next",
                    cand, exc,
                )
        # Exhausted every real candidate.
        if require_real:
            # Never silently emit degraded numbers: fail loudly so the report
            # cannot be mistaken for a verified real run.
            raise RuntimeError(
                f"Real embedding model {self.model_name!r} is required "
                f"(require_real_models=True) but no locally-cached real "
                f"sentence-transformers checkpoint could be loaded "
                f"({candidates}). Download one of these models first, or pick "
                f"an embedding model already present in the local cache."
            )
        logger.warning(
            "Could not load any locally-cached sentence-transformers model "
            "(requested %s). Falling back to local TF-IDF embedding "
            "(LOWER CONFIDENCE).",
            self.model_name,
        )
        self._init_fallback()

    # ------------------------------------------------------------------
    def _init_fallback(self):
        try:
            from sklearn.feature_extraction.text import HashingVectorizer
            from sklearn.preprocessing import Normalizer

            self._vec = HashingVectorizer(
                n_features=4096, alternate_sign=False, norm=None, ngram_range=(1, 2)
            )
            self._norm = Normalizer(norm="l2")
            self._kind = "tfidf-fallback"
            logger.info("using TF-IDF/hashing fallback embedder")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Neither sentence-transformers nor scikit-learn is available. "
                "Install with: pip install sentence-transformers scikit-learn"
            ) from exc

    # ------------------------------------------------------------------
    def encode(self, texts: Iterable[str], batch_size: int = 32,
               show_progress: bool = False) -> np.ndarray:
        texts = [t if isinstance(t, str) else str(t) for t in texts]
        texts = [t if t.strip() else " " for t in texts]
        if self._kind == "sentence-transformers":
            vecs = self._model.encode(
                texts, batch_size=batch_size, show_progress_bar=show_progress,
                convert_to_numpy=True, normalize_embeddings=True,
            )
            return np.asarray(vecs, dtype=np.float32)
        # fallback
        mats = self._vec.transform(texts)
        mats = self._norm.transform(mats)
        return np.asarray(mats.todense(), dtype=np.float32)

    @staticmethod
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        a = np.asarray(a, dtype=np.float32).ravel()
        b = np.asarray(b, dtype=np.float32).ravel()
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def kind(self) -> str:
        return self._kind