"""Tests for the entity-resolved transfer + verified social graph."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import networkx as nx
import pandas as pd

import build_cuyahoga_multilayer_graph as multilayer
import visualize_resolved_graph as viz
from splink_graph_pipeline import write_graphml


def _clusters() -> pd.DataFrame:
    rows = []
    for cluster_id, confidence, full_name, node_ids in [
        ("1", "HIGH", "ALICE SMITH", ["owner|A1", "owner|A2"]),
        ("2", "LOW", "BOB JONES", ["owner|B1", "owner|B2"]),
    ]:
        rows.extend({
            "node_id": node_id,
            "cluster_id": cluster_id,
            "full_name": full_name,
            "confidence_level": confidence,
        } for node_id in node_ids)
    return pd.DataFrame(rows)


def _inputs() -> tuple[nx.DiGraph, nx.Graph, pd.DataFrame]:
    transfer = nx.DiGraph()
    transfer.add_node("cluster:1", label="ALICE SMITH", resolved=True,
                      cluster_size=2, confidence_level="HIGH", kind="person_cluster")
    transfer.add_node("cluster:2", label="BOB JONES", resolved=True,
                      cluster_size=2, confidence_level="LOW", kind="person_cluster")
    transfer.add_edge(
        "cluster:1", "cluster:2", relation="transfer", weight=1,
        n_transactions=1, total_amount=75000.0, transactions=[{"transaction_id": "tx1"}],
    )

    unified = nx.Graph()
    unified.add_nodes_from([
        ("owner|UNRESOLVED A", {"kind": "person"}),
        ("owner|UNRESOLVED B", {"kind": "person"}),
    ])

    def social(source, target, relation, case_no):
        unified.add_edge(
            source, target, relation=relation, source="court_record",
            case_no=case_no, caption=f"Caption {case_no}", reliability="B",
            match_method="case_party_name",
        )

    social("owner|A1", "owner|B1", "married_to", "M-1")
    social("owner|A2", "owner|B2", "married_to", "M-1")
    social("owner|A1", "owner|B2", "litigated_with", "CV-1")
    social("owner|A2", "owner|B1", "divorced_from", "DR-1")
    social("owner|A1", "owner|A2", "divorced_from", "DR-SELF")
    social("owner|UNRESOLVED A", "owner|UNRESOLVED B", "mentioned_in_case", "CV-2")
    unified.add_edge("owner|B1", "owner|B2", relation="same_mail")
    return transfer, unified, _clusters()


def test_multilayer_merge_preserves_parallel_relations_and_provenance():
    graph, audit = multilayer.build_multilayer_graph(*_inputs())

    assert isinstance(graph, nx.MultiDiGraph)
    assert graph.number_of_edges() == 5
    relations = Counter(data["relation"] for _, _, data in graph.edges(data=True))
    assert relations == {
        "transfer": 1, "married_to": 1, "litigated_with": 1,
        "divorced_from": 1, "mentioned_in_case": 1,
    }
    cluster_pair_edges = list(graph.edges(("cluster:1", "cluster:2"), data=True))
    assert len(cluster_pair_edges) == 4

    married = next(data for _, _, data in graph.edges(data=True)
                   if data["relation"] == "married_to")
    assert married["directed"] is False
    assert married["n_source_edges"] == 2
    assert married["source_pairs"] == [
        {"source": "owner|A1", "target": "owner|B1"},
        {"source": "owner|A2", "target": "owner|B2"},
    ]
    transfer = next(data for _, _, data in graph.edges(data=True)
                    if data["relation"] == "transfer")
    assert transfer["directed"] is True
    assert transfer["transactions"] == [{"transaction_id": "tx1"}]

    assert audit["social_input_total"] == 6
    assert audit["social_output_total"] == 4
    assert audit["deduplicated_mapped_edges"] == {"married_to": 1}
    assert audit["collapsed_self_loops"] == {"divorced_from": 1}
    assert audit["collapsed_self_loop_records"][0]["case_no"] == "DR-SELF"
    assert audit["unresolved_unresolved_social_edges"] == {"mentioned_in_case": 1}
    assert audit["represented_source_social_edges"] == 5


def test_multilayer_graphml_round_trip_and_render(tmp_path: Path):
    graph, _ = multilayer.build_multilayer_graph(*_inputs())
    graph_path = tmp_path / "multilayer.graphml"
    clusters_path = tmp_path / "clusters.parquet"
    output_path = tmp_path / "multilayer.html"
    write_graphml(graph, graph_path)
    _clusters().to_parquet(clusters_path, index=False)

    loaded = nx.read_graphml(graph_path)
    assert isinstance(loaded, nx.MultiDiGraph)
    assert loaded.number_of_edges() == 5
    stats = viz.render_resolved_graph(graph_path, clusters_path, output_path)
    rendered = output_path.read_text(encoding="utf-8")

    assert stats == {"resolved_nodes": 2, "unresolved_context_nodes": 2, "edges": 5}
    assert "Entity-resolved multi-layer relationship graph" in rendered
    assert "Docket mention (not necessarily a litigant)" in rendered
    assert "CV-1" in rendered
    assert "owner|UNRESOLVED A" in rendered

    marker = "edges = new vis.DataSet("
    start = rendered.index(marker) + len(marker)
    edges, _ = json.JSONDecoder().raw_decode(rendered[start:])
    transfer = next(edge for edge in edges if "Property transfer" in edge["title"])
    marriage = next(edge for edge in edges if "<b>Marriage</b>" in edge["title"])
    mention = next(edge for edge in edges if "Docket mention" in edge["title"])
    assert transfer["arrows"]["to"]["enabled"] is True
    assert marriage["arrows"]["to"]["enabled"] is False
    assert marriage["color"] == "#ff1493"
    assert mention["dashes"] == [6, 4]
