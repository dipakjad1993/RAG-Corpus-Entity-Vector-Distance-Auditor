"""Local entity co-occurrence graph (knowledge graph).

Builds a directed-weighted graph of entity co-occurrence.  Two entities are
connected when they appear in the same paragraph of a retrieved document;
edge weight accumulates across the whole corpus.  This reveals how tightly
bound a competitor is to an industry topic versus how isolated the target
brand is -- the structural signal behind the RAG Invisibility Index.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

import networkx as nx

from ..utils import get_logger, normalize_text

logger = get_logger("ragevda.nlp.cooccurrence")


class CoOccurrenceGraph:
    def __init__(self) -> None:
        self.graph = nx.Graph()
        self._paragraph_cache: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------
    def _paragraphs(self, text: str) -> List[str]:
        # split document into paragraphs for finer co-occurrence resolution
        parts = [p for p in text.split("\n") if len(p.strip()) >= 20]
        if not parts:
            parts = [text]
        return parts

    def add_document(self, doc_id: str, text: str,
                     focus_entities: Optional[List[str]] = None) -> None:
        """Add one document's co-occurrence edges.

        ``focus_entities`` is the set of entities we definitely care about
        (brand + competitors + topics); they are always added as nodes even
        if a paragraph only contains one of them (self-loop avoided but they
        persist in the graph for later analysis).
        """
        focus = {e.lower(): e for e in (focus_entities or [])}
        for ent in focus.values():
            self.graph.add_node(ent, kind="focus")

        for para in self._paragraphs(text):
            para_low = para.lower()
            present: List[str] = []
            for low, orig in focus.items():
                if low in para_low:
                    present.append(orig)
            # also register any focus entity co-occurring with itself (node)
            for e in present:
                self.graph.add_node(e, kind="focus")
            # pairwise co-occurrence among focus entities
            for i in range(len(present)):
                for j in range(i + 1, len(present)):
                    a, b = present[i], present[j]
                    self.graph.add_edge(a, b)
                    self.graph[a][b]["weight"] = self.graph[a][b].get("weight", 0) + 1

    # ------------------------------------------------------------------
    def bind_strength(self, entity_a: str, entity_b: str) -> int:
        """Raw co-occurrence count between two entities (0 if none)."""
        a, b = entity_a.lower(), entity_b.lower()
        if self.graph.has_edge(a, b):
            return int(self.graph[a][b].get("weight", 0))
        return 0

    def neighbors(self, entity: str) -> Dict[str, int]:
        e = entity.lower()
        out: Dict[str, int] = {}
        if e in self.graph:
            for nb, data in self.graph[e].items():
                out[nb] = int(data.get("weight", 0))
        return out

    def topic_bind_strengths(self, entity: str, topics: List[str]) -> Dict[str, int]:
        """Co-occurrence weight between an entity and each target topic."""
        return {t: self.bind_strength(entity, t) for t in topics}

    def export_graphml(self, path: str) -> None:
        nx.write_graphml(self.graph, path)

    def stats(self) -> Dict:
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "density": round(nx.density(self.graph), 4),
        }
