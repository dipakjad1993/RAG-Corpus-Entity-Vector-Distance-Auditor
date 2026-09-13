"""Local Named Entity Recognition (NER) & mention detection.

Uses spaCy (free, open-source) to extract Organizations (ORG), Products
(PRODUCT), People (PERSON) and Geo-Political Entities (GPE) from every
document.  A lightweight regex/lexicon fallback keeps the pipeline alive if
the spaCy model is not installed.

In addition we provide deterministic *mention* detection for the specific
brand + competitor entities the operator cares about, which feeds the
citation-gap and co-occurrence analyses.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from ..utils import get_logger

logger = get_logger("ragevda.nlp.ner")

ENTITY_LABELS = ("ORG", "PRODUCT", "PERSON", "GPE", "WORK_OF_ART", "EVENT")


def _escape(phrase: str) -> str:
    return re.escape(phrase.strip())


class NER:
    # Locally-installed real spaCy models are preferred as fallbacks so the
    # audit never dies on a single unavailable model name while a real NER
    # checkpoint exists. Order = larger/better model first.
    FALLBACK_CHAIN = [
        "en_core_web_trf",
        "en_core_web_lg",
        "en_core_web_md",
        "xx_ent_wiki_sm",
        "en_core_web_sm",
    ]
    # Optional zero-shot product/sub-brand ontology extractor (GLiNER) — used
    # only when installed; spaCy remains the primary path. Keeps the existing
    # entity_aliases/ontology_aliases logic, just upgrades the model surface.
    GLINER_MODEL = "urchade/gliner_multi-v2.1"

    def __init__(self, model_name: str = "en_core_web_sm",
                 require_real: bool = False) -> None:
        self.model_name = model_name
        self._nlp = None
        self.used_model = None  # exact model actually loaded (for auditing)
        self._kind = "spacy"

        candidates = [model_name] + [
            m for m in self.FALLBACK_CHAIN if m != model_name
        ]
        import spacy
        from spacy.util import get_installed_models

        available = set(get_installed_models())
        for cand in candidates:
            if cand not in available:
                logger.info("spaCy model %s not installed; skip", cand)
                continue
            try:
                self._nlp = spacy.load(cand)
                self.used_model = cand
                self._kind = "spacy"
                logger.info("loaded spaCy model %s", cand)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "installed spaCy model %s failed to load (%s); trying next",
                    cand, exc,
                )

        # Exhausted every real installed model.
        if require_real:
            # Never silently emit degraded numbers: fail loudly so the report
            # cannot be mistaken for a verified real run.
            raise RuntimeError(
                f"Real NER model {model_name!r} is required "
                f"(require_real_models=True) but no locally-installed spaCy "
                f"model could be loaded ({candidates}). Install one with: "
                f"python -m spacy download en_core_web_sm"
            )
        logger.warning(
            "No installed spaCy model available (requested %s). Using regex "
            "fallback NER (LOWER CONFIDENCE).",
            model_name,
        )
        self._kind = "regex-fallback"

    def kind(self) -> str:
        return self._kind

    # ------------------------------------------------------------------
    def extract_entities(self, text: str) -> List[Tuple[str, str]]:
        """Return list of (entity_text, label) for the document."""
        if not text or len(text) < 3:
            return []
        if self._nlp is not None:
            try:
                doc = self._nlp(text[:1_000_000])
                out = []
                seen = set()
                for ent in doc.ents:
                    if ent.label_ in ENTITY_LABELS:
                        key = (ent.text.lower(), ent.label_)
                        if key not in seen:
                            seen.add(key)
                            out.append((ent.text, ent.label_))
                return out
            except Exception as exc:  # noqa: BLE001
                logger.warning("spaCy parse failed: %s", exc)

        # regex fallback: capitalized phrase sequences as ORG-ish candidates
        out = []
        for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b", text):
            phrase = m.group(1)
            if phrase.lower() in {"the", "this", "that", "we", "i", "it"}:
                continue
            out.append((phrase, "ORG"))
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def build_mention_patterns(entities: List[str],
                               aliases: Optional[Dict[str, List[str]]] = None
                               ) -> "tuple[Dict[str, re.Pattern], Dict[str, str]]":
        """Pre-compile case-insensitive word-boundary patterns.

        Returns ``(patterns, alias_to_entity)``:
        * ``patterns`` maps a lowercased key (entity name or alias) -> compiled regex
        * ``alias_to_entity`` maps every lowercased key back to the ORIGINAL entity
          string, so mention counts are attributed to the right entity even when an
          alias/domain variant was matched. This is what stops a brand being wrongly
          scored as "omitted" just because the page used a synonym.
        """
        aliases = aliases or {}
        patterns: Dict[str, re.Pattern] = {}
        alias_to_entity: Dict[str, str] = {}
        for e in entities:
            e = e.strip()
            if not e:
                continue
            elow = e.lower()
            if elow not in patterns:
                patterns[elow] = re.compile(
                    r"(?<![\w])" + _escape(e) + r"(?![\w])", re.IGNORECASE
                )
            alias_to_entity[elow] = e
            for a in aliases.get(e, []) or []:
                a = a.strip().lower()
                if a and a not in patterns:
                    patterns[a] = re.compile(
                        r"(?<![\w])" + _escape(a) + r"(?![\w])", re.IGNORECASE
                    )
                    alias_to_entity[a] = e
        return patterns, alias_to_entity

    @classmethod
    def find_mentions(cls, text: str, patterns: Dict[str, re.Pattern],
                      alias_to_entity: Optional[Dict[str, str]] = None) -> Counter:
        """Count occurrences of each target entity within text.

        Returns a Counter keyed by the ORIGINAL entity string (aliases are
        remapped via ``alias_to_entity``), so downstream code can use entity
        names directly instead of matching against alias substrings.
        """
        counts: Counter = Counter()
        if not text:
            return counts
        alias_to_entity = alias_to_entity or {}
        for key, pat in patterns.items():
            c = len(pat.findall(text))
            if c:
                counts[alias_to_entity.get(key, key)] += c
        return counts

    @staticmethod
    def entity_frequency(entities: List[Tuple[str, str]]) -> Counter:
        return Counter(e[0].lower() for e in entities)
