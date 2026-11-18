"""Graph-shape helpers shared by analysis, the agent, and the HTTP layer.

Directed graphs are valid inputs everywhere in the pipeline.  Connectivity
questions still need an undirected view; keeping that conversion in one place
prevents the ``NetworkXNotImplemented`` crashes that occurred when a Reddit
``DiGraph`` reached a function written for ``Graph``.
"""

from __future__ import annotations

import networkx as nx


def undirected_view(graph: nx.Graph) -> nx.Graph:
    """Return a cheap undirected view of ``graph``."""
    if graph.is_directed():
        return graph.to_undirected(as_view=True)
    return graph


def components(graph: nx.Graph) -> list[set]:
    """Connected components, using weak connectivity for directed graphs."""
    if graph.number_of_nodes() == 0:
        return []
    return list(nx.connected_components(undirected_view(graph)))


def component_count(graph: nx.Graph) -> int:
    return len(components(graph))


def largest_component(graph: nx.Graph) -> set:
    """Return the largest connected component, or an empty set for an empty graph."""
    found = components(graph)
    return max(found, key=len) if found else set()


def largest_subgraph(graph: nx.Graph) -> nx.Graph:
    """Copy of the largest connected component, preserving node attributes."""
    nodes = largest_component(graph)
    if not nodes:
        return undirected_view(graph).copy()
    return undirected_view(graph).subgraph(nodes).copy()
