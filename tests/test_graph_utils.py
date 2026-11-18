"""Regression tests for directed-graph handling in shared helpers."""

from __future__ import annotations

import networkx as nx

from osi.agent import _snapshot
from osi.analysis import network_health
from osi.graph_utils import (
    component_count,
    largest_component,
    largest_subgraph,
    undirected_view,
)


def _directed() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_edge("alice", "bob", weight=2.0)
    graph.add_edge("carol", "bob", weight=1.0)
    graph.add_edge("dave", "erin", weight=1.0)
    return graph


def test_components_use_weak_connectivity_for_directed_graphs():
    graph = _directed()
    assert component_count(graph) == 2
    assert largest_component(graph) == {"alice", "bob", "carol"}
    largest = largest_subgraph(graph)
    assert set(largest) == {"alice", "bob", "carol"}
    assert largest["alice"]["bob"]["weight"] == 2.0
    assert not largest.is_directed()


def test_undirected_view_keeps_the_original_graph_unchanged():
    graph = _directed()
    view = undirected_view(graph)
    assert view.is_directed() is False
    assert graph.is_directed() is True


def test_network_health_accepts_a_directed_graph():
    health = network_health(_directed())
    assert health["num_components"] == 2
    assert health["avg_degree"] == 1.2
    assert health["max_degree"] == 2
    assert 0.0 <= health["avg_clustering"] <= 1.0


def test_agent_snapshot_accepts_a_directed_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("OSI_STORE", str(tmp_path / "store.db"))
    snapshot = _snapshot("directed-v1", _directed())
    metrics = snapshot["finding_metrics"]
    assert metrics["nodes"] == 5
    assert metrics["edges"] == 3
    assert metrics["components"] == 2


def test_findings_and_failure_modes_count_weak_components():
    from osi.failure_modes import _with_defaults
    from osi.findings import _components as finding_components

    graph = _directed()
    assert finding_components({}, graph) == 2
    assert _with_defaults({}, graph)["components"] == 2


def test_hypotheses_accept_a_directed_graph():
    from osi.hypotheses import _has_sparse_cut

    graph = nx.DiGraph()
    graph.add_edges_from(
        [("a", "b"), ("b", "c"), ("c", "d"), ("d", "a")]
    )
    graph.add_edges_from(
        [("e", "f"), ("f", "g"), ("g", "h"), ("h", "e")]
    )
    assert _has_sparse_cut(graph) is True

