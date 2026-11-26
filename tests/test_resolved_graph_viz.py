"""Regression tests for the entity-resolved graph renderer."""

from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

import visualize_resolved_graph as viz


def _graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node("cluster:1", label="ALICE SMITH", resolved=True, cluster_size=2,
                   confidence_level="HIGH")
    graph.add_node("cluster:2", label="BOB JONES", resolved=True, cluster_size=1,
                   confidence_level="LOW")
    graph.add_node("cluster:3", label="ISOLATED CLUSTER", resolved=True, cluster_size=1,
                   confidence_level="LOW")
    graph.add_node("owner|ALICE A SMITH", resolved=False)
    graph.add_edge("cluster:1", "owner|ALICE A SMITH", weight=1, n_transactions=1)
    graph.add_edge("owner|ALICE A SMITH", "cluster:2", weight=2, n_transactions=2)
    graph.add_edge("owner|EXCLUDED", "owner|ALSO EXCLUDED")
    return graph


def test_resolved_neighborhood_keeps_isolates_and_only_direct_context():
    graph = viz.resolved_neighborhood(_graph())

    assert set(graph) == {
        "cluster:1", "cluster:2", "cluster:3", "owner|ALICE A SMITH"
    }
    assert graph.number_of_edges() == 2


def test_render_embeds_real_merged_nodes_and_member_provenance(tmp_path: Path):
    graph_path = tmp_path / "resolved.graphml"
    clusters_path = tmp_path / "clusters.parquet"
    output_path = tmp_path / "resolved.html"
    nx.write_graphml(_graph(), graph_path)
    pd.DataFrame([
        {"cluster_id": "1", "node_id": "owner|SMITH, ALICE", "full_name": "ALICE SMITH",
         "confidence_level": "HIGH"},
        {"cluster_id": "1", "node_id": "owner|A SMITH", "full_name": "A SMITH",
         "confidence_level": "HIGH"},
        {"cluster_id": "2", "node_id": "owner|JONES, BOB", "full_name": "BOB JONES",
         "confidence_level": "LOW"},
        {"cluster_id": "3", "node_id": "owner|ISOLATED", "full_name": "ISOLATED CLUSTER",
         "confidence_level": "LOW"},
    ]).to_parquet(clusters_path, index=False)

    stats = viz.render_resolved_graph(graph_path, clusters_path, output_path)
    rendered = output_path.read_text(encoding="utf-8")

    assert stats == {"resolved_nodes": 3, "unresolved_context_nodes": 1, "edges": 2}
    assert "cluster:1" in rendered
    assert "owner|SMITH, ALICE" in rendered
    assert "owner|A SMITH" in rendered
    assert "Entity-resolution members" in rendered
    assert '"enabled": false' in rendered
    assert "owner|EXCLUDED" not in rendered


def test_spacing_multiplier_increases_layout_distances():
    graph = nx.DiGraph([("cluster:1", "cluster:2")])
    compact = viz.packed_layout(graph, spacing=1.0)
    spacious = viz.packed_layout(graph, spacing=2.0)
    compact_span = max(x for x, _ in compact.values()) - min(x for x, _ in compact.values())
    spacious_span = max(x for x, _ in spacious.values()) - min(x for x, _ in spacious.values())

    assert spacious_span == pytest.approx(2 * compact_span)


def test_resolved_neighborhood_rejects_unresolved_input():
    with pytest.raises(ValueError, match="no entity-resolved"):
        viz.resolved_neighborhood(nx.DiGraph([("owner|A", "owner|B")]))
