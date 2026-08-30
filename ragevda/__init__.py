"""RAG Corpus Entity & Vector Distance Auditor (RAG-EVDA).

A zero-cost, local intelligence engine that audits how modern AI search
engines (Gemini, SearchGPT, Google AI Overviews) semantically perceive a
brand relative to its competitors inside a retrieval-augmented-generation
(RAG) corpus.

Package layout
--------------
ragevda.config         -> run configuration schema + loader
ragevda.harvester      -> zero-cost web harvesting (DuckDuckGo / SearXNG / local)
ragevda.nlp            -> embeddings, NER, co-occurrence graphs
ragevda.analysis       -> proximity, citation gaps, invisibility index, recs
ragevda.storage        -> DuckDB-backed corpus + vector store
ragevda.reporting      -> CSV / JSON / HTML dashboard
ragevda.orchestrator   -> end-to-end pipeline
ragevda.cli            -> command line entry point
"""

from .version import __version__

__all__ = ["__version__"]
