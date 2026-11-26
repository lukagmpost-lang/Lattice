"""Unit tests for the production Splink + graph pruning pipeline helpers."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

import splink_graph_pipeline as pipeline


def _person_frame(**overrides) -> pd.DataFrame:
    row = {
        "node_id": "Owner|SMITH, JOHN A",
        "surname": "Smith",
        "forename": "John",
        "middle_name": "Adam",
        "date_of_birth": "1980-01-01",
        "residential_address": "123 Main St, Cleveland, 44102",
        "zip": "44102-1234",
        "voter_registration_number": "OH0001",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_prepare_persons_maps_aliases_and_preserves_node_id_case():
    persons, stats = pipeline.prepare_persons(_person_frame())

    row = persons.iloc[0]
    assert row["node_id"] == "Owner|SMITH, JOHN A"
    assert row["first_name"] == "JOHN"
    assert row["last_name"] == "SMITH"
    assert row["middle_initial"] == "A"
    assert row["dob"] == "1980-01-01"
    assert row["address"] == "123 MAIN ST, CLEVELAND, 44102"
    assert row["zip_code"] == "44102"
    assert row["voter_id"] == "OH0001"
    assert row["full_name"] == "JOHN SMITH"
    assert stats["prepared_rows"] == 1


def test_prepare_persons_drops_rows_without_names():
    frame = pd.DataFrame(
        {
            "first_name": ["JOHN", ""],
            "last_name": ["SMITH", ""],
            "dob": ["1980-01-01", ""],
        }
    )
    persons, stats = pipeline.prepare_persons(frame)

    assert len(persons) == 1
    assert stats["dropped_blank_names"] == 1


def test_build_working_frame_turns_blanks_into_nulls():
    persons, _ = pipeline.prepare_persons(_person_frame())
    persons.loc[0, "middle_initial"] = ""
    working = pipeline.build_working_frame(persons)

    assert pd.isna(working.loc[0, "middle_initial"])
    assert working.loc[0, "first_name"] == "JOHN"
    assert list(working.columns) == ["unique_id", *pipeline.CANONICAL_COLUMNS]


def test_cluster_audit_counts_and_top_clusters():
    clustered = pd.DataFrame(
        {
            "cluster_id": ["a", "a", "b", "c", "c", "c"],
            "node_id": ["n1", "n2", "n3", "n4", "n5", "n6"],
        }
    )
    audit = pipeline.cluster_audit(clustered)

    assert audit["total_records"] == 6
    assert audit["total_clusters"] == 3
    assert audit["multi_record_clusters"] == 2
    assert audit["records_in_multi_clusters"] == 5
    assert audit["singleton_clusters"] == 1
    assert audit["largest_cluster_size"] == 3
    assert audit["top_clusters"][0]["cluster_id"] == "c"
    assert audit["top_clusters"][0]["node_ids"] == ["n4", "n5", "n6"]


def _person(unique_id: int, cluster_id: int, **overrides) -> dict:
    row = {
        "unique_id": unique_id,
        "cluster_id": cluster_id,
        "node_id": f"n{unique_id}",
        "first_name": "JOHN",
        "last_name": "SMITH",
        "middle_initial": "",
        "dob": "",
        "address": "1 MAIN ST, CLEVELAND, 44102",
        "voter_id": "",
    }
    row.update(overrides)
    return row


def _cluster_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _cluster_map(frame: pd.DataFrame) -> dict[int, int]:
    return dict(zip(frame.unique_id, frame.cluster_id))


def test_split_conflicting_clusters_splits_identifier_conflicts():
    clustered = _cluster_frame(
        [
            # Same DOB, voter ID, and middle initial: compatible.
            _person(1, 10, dob="1980-01-01", voter_id="V1", middle_initial="A"),
            _person(2, 10, dob="1980-01-01", voter_id="V1", middle_initial="A"),
            # Different DOB.
            _person(3, 10, dob="1990-01-01", voter_id="V3", middle_initial="C"),
            # Different voter ID only.
            _person(4, 11, voter_id="V4"),
            _person(5, 11, voter_id="V5"),
            # Different middle initial only.
            _person(6, 12, middle_initial="J"),
            _person(7, 12, middle_initial="K"),
            # Missing identifiers never conflict when the record is not a ghost.
            _person(8, 13),
            _person(9, 13),
        ]
    )

    refined, stats = pipeline.split_conflicting_clusters(clustered)
    clusters = _cluster_map(refined)

    assert clusters[1] == clusters[2] == 10
    assert clusters[3] != 10
    assert clusters[4] != clusters[5]
    assert clusters[6] != clusters[7]
    assert clusters[8] == clusters[9] == 13
    assert stats["split_clusters"] == 3
    assert stats["conflicts"] == {"dob": 2, "voter_id": 1, "middle_initial": 1}


def test_split_conflicting_clusters_never_groups_a_conflicting_pair():
    clustered = _cluster_frame(
        [
            # A-B compatible and B-C compatible, but A-C conflict.
            _person(1, 20, dob="1980-01-01"),
            _person(2, 20),
            _person(3, 20, dob="1990-01-01"),
        ]
    )

    refined, _ = pipeline.split_conflicting_clusters(clustered)
    clusters = _cluster_map(refined)

    assert clusters[1] != clusters[3]
    assert len(set(clusters.values())) == 2


def test_split_conflicting_clusters_treats_pd_na_as_missing():
    clustered = _cluster_frame(
        [
            _person(1, 25, dob="1980-01-01", voter_id="V1", middle_initial="A"),
            _person(
                2,
                25,
                dob=pd.NA,
                voter_id=pd.NA,
                middle_initial=pd.NA,
            ),
        ]
    )

    refined, stats = pipeline.split_conflicting_clusters(clustered)

    assert refined["cluster_id"].nunique() == 1
    assert stats["split_clusters"] == 0


def test_first_name_rule_splits_different_names_without_shared_identifier():
    clustered = _cluster_frame(
        [
            # Different first names, same last name, no shared identifiers.
            _person(1, 40, first_name="ANTONIO", last_name="FLORES"),
            _person(2, 40, first_name="FELIX", last_name="FLORES"),
            _person(3, 40, first_name="RICHARD", last_name="FLORES"),
            # Same DOB permits different first names.
            _person(
                4,
                41,
                first_name="ANTONIO",
                last_name="FLORES",
                dob="1980-01-01",
            ),
            _person(
                5,
                41,
                first_name="FELIX",
                last_name="FLORES",
                dob="1980-01-01",
            ),
            # Same voter ID permits different first names.
            _person(
                6,
                42,
                first_name="DORELA",
                last_name="CELA",
                voter_id="V6",
            ),
            _person(
                7,
                42,
                first_name="ERMIRA",
                last_name="CELA",
                voter_id="V6",
            ),
        ]
    )

    refined, stats = pipeline.split_conflicting_clusters(clustered)
    clusters = _cluster_map(refined)

    assert len({clusters[1], clusters[2], clusters[3]}) == 3
    assert clusters[4] == clusters[5]
    assert clusters[6] == clusters[7]
    assert stats["conflicts"]["first_name"] == 3


def test_first_name_rule_allows_prefix_variants():
    clustered = _cluster_frame(
        [
            _person(1, 43, first_name="JOHN"),
            _person(2, 43, first_name="JOHNATHAN"),
        ]
    )

    refined, stats = pipeline.split_conflicting_clusters(clustered)

    assert refined["cluster_id"].nunique() == 1
    assert stats["split_clusters"] == 0


def test_ghost_records_are_forced_to_singletons():
    clustered = _cluster_frame(
        [
            # A ghost plus a fully identified record with the same name.
            _person(1, 50, first_name="DAVID", last_name="MILLER", address=""),
            _person(
                2,
                50,
                first_name="DAVID",
                last_name="MILLER",
                dob="1957-05-11",
                voter_id="V2",
            ),
            # Two ghosts with the same name must each be isolated.
            _person(3, 51, first_name="DAVID", last_name="MILLER", address=""),
            _person(4, 51, first_name="DAVID", last_name="MILLER", address=""),
        ]
    )

    refined, stats = pipeline.split_conflicting_clusters(clustered)
    sizes = refined.groupby("cluster_id").size()

    ghost_ids = refined.loc[refined.unique_id.isin([1, 3, 4]), "cluster_id"]
    assert ghost_ids.nunique() == 3
    assert all(sizes[cluster_id] == 1 for cluster_id in ghost_ids)
    assert stats["ghost_records"] == 3
    assert stats["ghost_records_split"] == 2


def test_split_conflicting_clusters_assigns_confidence_levels():
    clustered = _cluster_frame(
        [
            # HIGH: members share a voter ID.
            _person(1, 30, voter_id="V1"),
            _person(2, 30, voter_id="V1"),
            # LOW: name-only, no identifiers at all.
            _person(3, 31),
            _person(4, 31),
        ]
    )

    refined, stats = pipeline.split_conflicting_clusters(clustered)

    assert refined.loc[refined.unique_id == 1, "confidence_level"].iloc[0] == "HIGH"
    assert refined.loc[refined.unique_id == 2, "confidence_level"].iloc[0] == "HIGH"
    assert refined.loc[refined.unique_id == 3, "confidence_level"].iloc[0] == "LOW"
    assert refined.loc[refined.unique_id == 4, "confidence_level"].iloc[0] == "LOW"
    assert stats["high_confidence_clusters"] == 1
    assert stats["low_confidence_clusters"] == 1


def test_write_cluster_parquet_carries_confidence_and_split_ids(tmp_path: Path):
    persons = pd.DataFrame(
        [
            {"node_id": "owner|A", "unique_id": 1, "first_name": "A", "last_name": "X"},
            {"node_id": "owner|B", "unique_id": 2, "first_name": "B", "last_name": "X"},
        ]
    )
    clusters = pd.DataFrame(
        [
            {"unique_id": 1, "cluster_id": 5, "splink_cluster_id": 5, "confidence_level": "HIGH"},
            {"unique_id": 2, "cluster_id": 5, "splink_cluster_id": 5, "confidence_level": "HIGH"},
        ]
    )

    merged = pipeline.write_cluster_parquet(persons, clusters, path=tmp_path / "clusters.parquet")

    assert merged["cluster_size"].tolist() == [2, 2]
    assert merged["confidence_level"].tolist() == ["HIGH", "HIGH"]
    assert merged["splink_cluster_id"].tolist() == [5, 5]
    written = pd.read_parquet(tmp_path / "clusters.parquet")
    assert "confidence_level" in written.columns


def test_prune_graph_keeps_all_cycles_and_paths_to_them():
    graph = pipeline.create_sample_graph()
    pruned, stats = pipeline.prune_graph_preserve_chains(graph)

    assert set(pruned.nodes()) == {"A", "B", "C", "D", "E", "F", "G", "H"}
    assert pruned.number_of_edges() == 9
    assert stats["cycles"] == 2
    assert stats["cycle_nodes"] == 6
    assert stats["removed_nodes"] == 5


def test_prune_graph_keeps_disconnected_cycles_and_self_loops():
    graph = nx.DiGraph()
    graph.add_edge("a", "b")
    graph.add_edge("b", "a")
    graph.add_edge("x", "x")
    graph.add_edge("dead", "end")
    pruned, stats = pipeline.prune_graph_preserve_chains(graph)

    assert set(pruned.nodes()) == {"a", "b", "x"}
    assert stats["cycles"] == 2


def test_prune_graph_accepts_an_empty_graph():
    pruned, stats = pipeline.prune_graph_preserve_chains(
        nx.DiGraph(), progress=False
    )

    assert pruned.number_of_nodes() == 0
    assert stats["cycles"] == 0
    assert stats["removed_nodes"] == 0


def test_build_cluster_graph_collapses_parallel_edges():
    graph = nx.DiGraph()
    # Distinct source variants collapse onto the same cluster, which is the
    # parallel-edge case created by entity resolution.
    graph.add_edge(
        "owner|A1", "owner|B1", weight=1, total_amount=10.0, book_pages=["BP1"]
    )
    graph.add_edge(
        "owner|A2", "owner|B1", weight=2, total_amount=5.0, book_pages=["BP2", "BP3"]
    )
    graph.add_edge("owner|B1", "owner|A1", weight=1, total_amount=1.0)

    cluster_graph, stats = pipeline.build_cluster_graph(
        graph,
        {"owner|A1": "10", "owner|A2": "10", "owner|B1": "11"},
        cluster_labels={"10": "A PERSON", "11": "B PERSON"},
    )

    assert set(cluster_graph.nodes()) == {"cluster:10", "cluster:11"}
    edge = cluster_graph["cluster:10"]["cluster:11"]
    assert edge["weight"] == 3
    assert edge["total_amount"] == 15.0
    assert edge["n_transactions"] == 3
    assert edge["book_pages"] == ["BP1", "BP2", "BP3"]
    assert cluster_graph.nodes["cluster:10"]["label"] == "A PERSON"
    assert cluster_graph.nodes["cluster:10"]["cluster_size"] == 2
    assert stats["output_edges"] == 2
    assert stats["resolved_nodes"] == 3
    assert not stats["transaction_provenance_complete"]


def test_build_cluster_graph_deduplicates_joint_party_transaction_ids():
    transaction = {
        "transaction_id": "tx-1",
        "source_row": 0,
        "parcel_id": "P1",
        "date": "2024-01-02",
        "amount": 100.0,
        "book_page": "BP1",
    }
    graph = nx.DiGraph()
    graph.add_edge(
        "owner|A1", "owner|B1", weight=1, total_amount=100.0,
        book_pages=["BP1"], transactions=[transaction],
    )
    graph.add_edge(
        "owner|A2", "owner|B1", weight=1, total_amount=100.0,
        book_pages=["BP1"], transactions=[transaction],
    )

    cluster_graph, stats = pipeline.build_cluster_graph(
        graph,
        {"owner|A1": "10", "owner|A2": "10", "owner|B1": "11"},
    )

    edge = cluster_graph["cluster:10"]["cluster:11"]
    assert edge["weight"] == 1
    assert edge["n_transactions"] == 1
    assert edge["party_pair_weight"] == 2
    assert edge["total_amount"] == 100
    assert edge["book_pages"] == ["BP1"]
    assert edge["transactions"] == [transaction]
    assert edge["first_date"] == "2024-01-02"
    assert edge["last_date"] == "2024-01-02"
    assert stats["transaction_provenance_complete"]


def test_build_cluster_graph_preserves_unresolved_endpoints_and_counts_actual_mappings():
    graph = nx.DiGraph()
    graph.add_edge("owner|A", "owner|UNKNOWN", weight=2, total_amount=10)
    graph.add_node("owner|ISOLATED")

    cluster_graph, stats = pipeline.build_cluster_graph(
        graph,
        {"owner|A": "10", "owner|NOT_IN_GRAPH": "11"},
    )

    assert cluster_graph.has_edge("cluster:10", "owner|UNKNOWN")
    assert not cluster_graph.nodes["owner|UNKNOWN"]["resolved"]
    assert stats["resolution_mappings"] == 2
    assert stats["resolved_nodes"] == 1
    assert stats["unresolved_input_nodes"] == 2


def test_write_graphml_sanitizes_attributes_and_round_trips(tmp_path: Path):
    graph = nx.DiGraph()
    graph.add_node("a", label="A", tags=["x", "y"], meta={"k": 1})
    graph.add_node("b", label=None, resolved=True)
    graph.add_edge("a", "b", weight=1.5, note=None)

    path = tmp_path / "graph.graphml"
    stats = pipeline.write_graphml(graph, path)

    assert path.exists()
    assert stats == {"graphml_nodes": 2, "graphml_edges": 1}
    loaded = nx.read_graphml(path)
    assert loaded.number_of_nodes() == 2
    assert loaded.number_of_edges() == 1
    assert loaded.nodes["a"]["tags"] == json.dumps(["x", "y"])
    assert loaded.nodes["b"]["label"] == ""
    assert loaded.edges["a", "b"]["note"] == ""


def test_shared_settings_are_the_golden_settings():
    from osi.splink_config import BLOCKING_RULES, build_settings

    settings = pipeline.build_splink_settings()
    rules = settings.blocking_rules_to_generate_predictions

    assert len(rules) == len(BLOCKING_RULES) == 4
    assert len(settings.comparisons) == 8
    assert build_settings().unique_id_column_name == "unique_id"


def test_load_graph_rejects_undirected(tmp_path: Path):
    graph = nx.Graph()
    graph.add_edge("a", "b")
    path = tmp_path / "undirected.pkl"
    import pickle

    with path.open("wb") as handle:
        pickle.dump(graph, handle)

    with pytest.raises(TypeError):
        pipeline.load_graph(path)


def test_load_graph_requires_real_input_unless_demo_is_explicit():
    with pytest.raises(ValueError, match="--demo"):
        pipeline.load_graph(None)

    demo = pipeline.load_graph(None, demo=True)
    assert set(demo.nodes()) == set(pipeline.create_sample_graph().nodes())


def test_graphml_preserves_transaction_provenance(tmp_path: Path):
    graph = nx.DiGraph()
    graph.add_edge(
        "a",
        "b",
        book_pages=["BP1", "BP1"],
        transactions=[
            {"transaction_id": "tx-1", "amount": 10.0, "book_page": "BP1"},
            {"transaction_id": "tx-2", "amount": 20.0, "book_page": "BP1"},
        ],
    )
    path = tmp_path / "provenance.graphml"

    pipeline.write_graphml(graph, path)
    loaded = nx.read_graphml(path)

    edge = loaded["a"]["b"]
    assert json.loads(edge["book_pages"]) == ["BP1", "BP1"]
    assert [
        item["transaction_id"] for item in json.loads(edge["transactions"])
    ] == ["tx-1", "tx-2"]
