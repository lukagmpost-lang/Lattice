"""Compute corroboration counts for pairs of nodes in the OSI graph.

Estorides' confidence model treats corroboration as the dominant term: an
observation from a single source scores low regardless of how reliable that
source is. Independence is what raises confidence, and independence means
*different record systems*, not different relation names.

This module defines:

- ``RELATION_FAMILY``: which record system produced each OSI edge relation.
- ``corroboration_count(graph, u, v)``: how many distinct families connect
  the pair, excluding contradictions (namesake).
- ``confidence_for_pair(graph, u, v, relation)``: the confidence of one
  specific edge, with its corroboration_count derived from the pair's
  overall evidence rather than passed in by hand.
"""
from __future__ import annotations

import networkx as nx

from .adapter import edge_confidence

# Relation -> record-system family. Two relations in the same family
# do NOT corroborate each other; only distinct families count.
RELATION_FAMILY: dict[str, str] = {
    # Deed / parcel fabric: county recorder and fiscal office records.
    "owns":                   "deed",
    "sold_to":                "deed",
    "signed_for":             "deed",
    # Ohio Secretary of State filings.
    "statutory_agent_of":     "sos",
    "officer_of":             "sos",
    "registered_as":          "sos",
    # Cuyahoga Clerk of Courts foreclosure filings (NEO CANDO).
    "defendant_in":           "court",
    "foreclosed_on":          "court",
    # Derived from primary records by this repo's own scripts.
    "co_owner":               "derivation",
    "same_mail":              "derivation",
    # Independent reference (Wikipedia / Wikidata sitelink).
    "wikipedia_corroborated": "reference",
    # Algorithmic candidates from OsintHunter.
    "has_alias":              "osint",
    "probable_identity":      "osint",
    # Explicit contradiction: excluded from corroboration entirely.
    "namesake":               None,
}


def relation_family(relation: str) -> str | None:
    """Return the record-system family for a relation, or None if excluded."""
    return RELATION_FAMILY.get(relation)


def corroboration_count(graph: nx.Graph, u, v) -> int:
    """Count distinct record-system families connecting u and v.

    Contradictions (namesake) are excluded. A pair with no edges or only
    contradiction edges returns 0; the caller decides whether to score at
    corroboration_count=1 for the edge being evaluated.
    """
    if not graph.has_edge(u, v):
        return 0
    families = set()
    for relation in _all_relations(graph, u, v):
        fam = relation_family(relation)
        if fam is not None:
            families.add(fam)
    return len(families)


def _all_relations(graph: nx.Graph, u, v) -> list[str]:
    """Return every relation name carried by the (u, v) edge."""
    if not graph.has_edge(u, v):
        return []
    data = graph[u][v]
    rel = data.get("relation")
    if rel is None:
        return []
    return [r.strip() for r in str(rel).split(" | ") if r.strip()]


def confidence_for_pair(graph: nx.Graph, u, v, relation: str) -> float:
    """Score one edge, with corroboration derived from the pair's evidence.

    The corroboration_count is ``max(corroboration_count(graph, u, v), 1)``
    so an isolated edge still gets scored against the single-source tier
    rather than zero.

    Adds +1 to the family count when the edge itself is ``wikipedia_corroborated``
    and the pair has other evidence, so the Wikipedia check is treated as an
    independent reference on top of the relation's own family.
    """
    n = max(corroboration_count(graph, u, v), 1)
    return edge_confidence(relation, corroboration_count=n)


if __name__ == "__main__":
    import networkx as nx

    print("=== family map ===")
    seen = set()
    for rel, fam in sorted(RELATION_FAMILY.items(), key=lambda x: (x[1] or "zzz", x[0])):
        print(f"  {rel:24s} -> {fam or '(excluded)'}")
        seen.add(fam)

    print()
    print("=== LAUDI <-> DIMACCHIA (co_owner + same_mail, both derivation) ===")
    G = nx.Graph()
    G.add_edge("LAUDI", "DIMACCHIA", relation="co_owner")
    G.add_edge("LAUDI", "DIMACCHIA", relation="same_mail")
    # NetworkX merges multi-edges; simulate the " | " format used by the loader
    G["LAUDI"]["DIMACCHIA"]["relation"] = "co_owner | same_mail"
    n = corroboration_count(G, "LAUDI", "DIMACCHIA")
    print(f"  corroboration_count = {n}  (expected 1: both derivation)")
    print(f"  co_owner confidence = {confidence_for_pair(G, 'LAUDI', 'DIMACCHIA', 'co_owner'):.4f}")

    print()
    print("=== LAUDI <-> JAMSERIES (signed_for + registered_as, deed + sos) ===")
    G2 = nx.Graph()
    G2.add_edge("LAUDI", "JAMSERIES", relation="signed_for | registered_as")
    n2 = corroboration_count(G2, "LAUDI", "JAMSERIES")
    print(f"  corroboration_count = {n2}  (expected 2: deed + sos)")
    print(f"  signed_for confidence = {confidence_for_pair(G2, 'LAUDI', 'JAMSERIES', 'signed_for'):.4f}")

    print()
    print("=== LAUDI <-> BROOKLYN (co_owner + namesake) ===")
    G3 = nx.Graph()
    G3.add_edge("LAUDI", "BROOKLYN", relation="co_owner | namesake")
    n3 = corroboration_count(G3, "LAUDI", "BROOKLYN")
    print(f"  corroboration_count = {n3}  (expected 1: namesake excluded, co_owner only)")
    print(f"  co_owner confidence = {confidence_for_pair(G3, 'LAUDI', 'BROOKLYN', 'co_owner'):.4f}")
    print("  (the namesake contradiction is NOT applied here — that requires")
    print("   resolve_with_contradictions() from adapter.py, not this function)")
