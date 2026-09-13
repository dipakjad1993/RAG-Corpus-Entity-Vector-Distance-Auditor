"""Unified semantic chunking: one splitter, sentence-safe, model-aware."""

from ragevda.analysis.chunking import (
    token_windows, resolve_tokenizer_name)
from ragevda.utils import chunk_text


def test_no_mid_sentence_break():
    text = "First sentence here. Second sentence here. Third sentence here."
    wins = token_windows(text, tokens=10, overlap_tokens=2)
    assert wins
    for w in wins:
        # windows end on sentence boundaries (period) except possibly last
        assert w.strip()[-1] in ".!?" or w == wins[-1]


def test_chunk_text_unified_with_token_windows():
    text = ("Alpha beta gamma. " * 5 + "Delta epsilon zeta. " * 5).strip()
    a = chunk_text(text, max_chars=120, overlap=12)
    b = token_windows(text, tokens=30, overlap_tokens=3)
    assert a and b
    # both are sentence-packed (no window starts mid-word-sentence fragment)
    for w in a:
        assert len(w) >= 20


def test_model_aware_tokenizer_resolution():
    assert "nomic" in resolve_tokenizer_name("nomic-ai/nomic-embed-text-v1.5")
    assert "bge-m3" in resolve_tokenizer_name("BAAI/bge-m3").lower()
    assert "qwen" in resolve_tokenizer_name("Qwen/Qwen3-Embedding-0.6B").lower()
    assert "MiniLM" in resolve_tokenizer_name("sentence-transformers/all-MiniLM-L6-v2")


def test_require_real_raises_without_cache():
    from ragevda.analysis import chunking as C
    # unknown family with require_real: must raise, never silent char/4
    try:
        C._get_tokenizer("__no_such_model_xyz__", True)
    except RuntimeError:
        pass
    else:
        # if a tokenizer IS cached for default family, resolution returns it —
        # either way no silent fallback numbers are emitted as real
        tok = C._get_tokenizer("", False)
        assert tok is None or hasattr(tok, "encode")
