"""Co-occurrence graph: capitalized entities bind (regression test).

v1.2.0 fixed a case bug where bind_strength() was always 0 for real
capitalized brand names. No network, no models (networkx only).
"""

from ragevda.nlp.cooccurrence import CoOccurrenceGraph


def _graph():
    g = CoOccurrenceGraph()
    g.add_document(
        "d1",
        "Apple and Microsoft partner on AI cloud.\nApple launches Vision.",
        ["Apple", "Microsoft", "AI cloud"],
    )
    return g


def test_bind_strength_nonzero():
    g = _graph()
    assert g.bind_strength("Apple", "Microsoft") == 1


def test_case_insensitive_lookup():
    g = _graph()
    assert g.bind_strength("apple", "microsoft") == 1
    assert g.bind_strength("APPLE", "MICROSOFT") == 1


def test_neighbors():
    g = _graph()
    assert g.neighbors("Apple")["Microsoft"] == 1


def test_stats_shape():
    g = _graph()
    s = g.stats()
    assert s["nodes"] == 3 and s["edges"] >= 1
