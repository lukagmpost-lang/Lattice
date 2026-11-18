"""Regression tests for the verified Cuyahoga court/marriage merge."""

from __future__ import annotations

import pickle

import networkx as nx

from osi.loaders.merge_jsonl_to_graph import (
    PersonIndex,
    merge_courts,
    merge_marriages,
    rebuild_source_edges,
    resolve_party_node,
    run,
)


def _graph():
    graph = nx.Graph()
    graph.add_node(
        "owner|JR, HENRY C",
        type="owner",
        kind="person",
        name="HENRY CURRIE JR",
        date_of_birth="1950-01-01",
    )
    graph.add_node(
        "owner|SMITH, JOHN",
        type="owner",
        kind="person",
        name="SMITH, JOHN",
        date_of_birth="1980-01-01",
    )
    return graph


TARGETS = {
    "owner|JR, HENRY C": {"last": "CURRIE", "first": "HENRY"},
    "owner|SMITH, JOHN": {"last": "SMITH", "first": "JOHN"},
}


def test_marriage_requires_the_target_in_the_case():
    graph = _graph()
    records = [
        {
            "status": "success",
            "node_key": "owner|JR, HENRY C",
            "parties": [
                {"case": "2010ML1", "parties": ["HENRY CURRIE JR", "MARY JONES"]},
                # Neither party is the searched person; this used to create a
                # spouse-spouse edge between two unrelated people.
                {"case": "2011ML2", "parties": ["ALICE BROWN", "BOB GREEN"]},
            ],
        }
    ]
    stats = merge_marriages(graph, records, TARGETS)

    assert stats["added"] == 1
    assert stats["unverified"] == 1
    assert graph.has_edge("owner|JR, HENRY C", "owner|JONES, MARY")
    assert not graph.has_edge("owner|BROWN, ALICE", "owner|GREEN, BOB")
    edge = graph["owner|JR, HENRY C"]["owner|JONES, MARY"]
    assert edge["relation"] == "married_to"
    assert edge["reliability"] == "B"
    assert edge["case_no"] == "2010ML1"


def test_marriage_with_target_identified_by_metadata_despite_bad_key():
    graph = _graph()
    records = [
        {
            "status": "success",
            "node_key": "owner|JR, HENRY C",
            "parties": [{"case": "2012ML3", "parties": ["MARY JONES", "HENRY CURRIE"]}],
        }
    ]
    stats = merge_marriages(graph, records, TARGETS)
    assert stats["added"] == 1
    assert graph.has_edge("owner|JR, HENRY C", "owner|JONES, MARY")


def test_court_requires_target_in_caption_and_uses_the_other_side():
    graph = _graph()
    records = [
        {
            "status": "success",
            "node_key": "owner|SMITH, JOHN",
            "rows": [
                {
                    "name": "SMITH JOHN",
                    "role": "PLAINTIFF",
                    "case_num": "DR-16-12345",
                    "caption": "JOHN SMITH v JANE ROE",
                },
                {
                    # The searched name appears in the result row, but not in
                    # the caption.  No edge is allowed.
                    "name": "SMITH JOHN",
                    "role": "DEFENDANT",
                    "case_num": "CV-20-1",
                    "caption": "ACME LLC v ROBERT ROE",
                },
                {
                    "name": "SMITH JOHN",
                    "role": "DEFENDANT",
                    "case_num": "CV-20-2",
                    "caption": "JANE ROE v JOHN SMITH ET AL",
                },
            ],
        }
    ]
    stats = merge_courts(graph, records, TARGETS)

    assert stats["added"] == 1
    assert stats["unverified"] == 1
    assert graph.has_edge("owner|SMITH, JOHN", "owner|ROE, JANE")
    edge = graph["owner|SMITH, JOHN"]["owner|ROE, JANE"]
    assert edge["relation"] == "divorced_from"
    assert edge["reliability"] == "B"


def test_court_underage_target_is_skipped():
    graph = _graph()
    graph.nodes["owner|SMITH, JOHN"]["date_of_birth"] = "2010-01-01"
    records = [
        {
            "status": "success",
            "node_key": "owner|SMITH, JOHN",
            "rows": [
                {
                    "name": "SMITH JOHN",
                    "role": "PLAINTIFF",
                    "case_num": "DR-16-12345",
                    "caption": "JOHN SMITH v JANE ROE",
                }
            ],
        }
    ]
    stats = merge_courts(graph, records, TARGETS)
    assert stats["underage"] == 1
    assert stats["added"] == 0
    assert not graph.has_edge("owner|SMITH, JOHN", "owner|ROE, JANE")


def test_court_no_rows_is_counted_separately():
    graph = _graph()
    records = [
        {"status": "success", "node_key": "owner|SMITH, JOHN", "rows": []}
    ]
    stats = merge_courts(graph, records, TARGETS)
    assert stats["no_rows"] == 1
    assert stats["added"] == 0


def test_resolve_party_does_not_prefix_merge_different_surnames():
    graph = nx.Graph()
    graph.add_node("owner|PAGAN, JOSE", type="owner", kind="person", name="PAGAN, JOSE")
    index = PersonIndex(graph)
    key = resolve_party_node(graph, index, "JOSE PAGANO", source="court_record")
    assert key == "owner|PAGANO, JOSE"
    assert key != "owner|PAGAN, JOSE"
    assert key in graph

    # A second identical name reuses the node instead of creating a duplicate.
    again = resolve_party_node(graph, index, "JOSE PAGANO", source="court_record")
    assert again == key


def test_rebuild_removes_only_source_edges():
    graph = _graph()
    graph.add_edge(
        "owner|JR, HENRY C",
        "owner|JONES, MARY",
        relation="married_to",
        source="marriage_record",
        reliability="A",
    )
    graph.add_edge(
        "owner|SMITH, JOHN",
        "owner|ROE, JANE",
        relation="litigated_with",
        source="court_record",
        reliability="A",
    )
    graph.add_edge(
        "owner|JR, HENRY C",
        "owner|SMITH, JOHN",
        relation="same_mail",
    )
    removed = rebuild_source_edges(graph)
    assert removed == 2
    assert not graph.has_edge("owner|JR, HENRY C", "owner|JONES, MARY")
    assert not graph.has_edge("owner|SMITH, JOHN", "owner|ROE, JANE")
    assert graph.has_edge("owner|JR, HENRY C", "owner|SMITH, JOHN")


def test_run_dry_run_does_not_write(tmp_path):
    graph_path = tmp_path / "graph.pkl"
    with graph_path.open("wb") as handle:
        pickle.dump(_graph(), handle)
    before = graph_path.read_bytes()

    summary = run(
        graph_path=graph_path,
        marriage_path=tmp_path / "missing-marriage.jsonl",
        courts_path=tmp_path / "missing-courts.jsonl",
        targets_path=None,
        apply=False,
    )
    assert "written" not in summary
    assert graph_path.read_bytes() == before
