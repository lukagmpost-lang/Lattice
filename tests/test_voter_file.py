"""Regression tests for voter-file identity enrichment."""

from __future__ import annotations

import csv

import networkx as nx

from osi.loaders import voter_file


def _voter_csv(path, rows):
    fields = [
        "SOS_VOTERID",
        "LAST_NAME",
        "FIRST_NAME",
        "MIDDLE_NAME",
        "DATE_OF_BIRTH",
        "VOTER_STATUS",
        "PARTY_AFFILIATION",
        "RESIDENTIAL_ADDRESS1",
        "RESIDENTIAL_CITY",
        "RESIDENTIAL_ZIP",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_name_parts_strip_generational_suffix():
    assert voter_file.name_parts_graph("CURRIE, HENRY JR") == ("CURRIE", "HENRY", "")
    assert voter_file.name_parts_graph("HENRY CURRIE JR") == ("CURRIE", "HENRY", "")


def test_dob_key_normalizes_common_formats():
    assert voter_file._dob_key("09/10/1989") == "1989-09-10"
    assert voter_file._dob_key("1989-09-10") == "1989-09-10"
    assert voter_file._dob_key("19890910") == "1989-09-10"


def test_match_vocabulary_is_stable(tmp_path):
    path = tmp_path / "voters.csv"
    _voter_csv(
        path,
        [
            {
                "SOS_VOTERID": "OH1",
                "LAST_NAME": "CURRIE",
                "FIRST_NAME": "HENRY",
                "MIDDLE_NAME": "",
                "DATE_OF_BIRTH": "09/10/1950",
                "VOTER_STATUS": "ACTIVE",
                "PARTY_AFFILIATION": "D",
                "RESIDENTIAL_ADDRESS1": "1 MAIN ST",
                "RESIDENTIAL_CITY": "CLEVELAND",
                "RESIDENTIAL_ZIP": "44102",
            }
        ],
    )
    index = voter_file.build_voter_index(path)
    match, records = voter_file.match_node(
        "CURRIE, HENRY", {}, set(), index
    )
    assert match == voter_file.MATCH_NAME_UNIQUE
    assert records[0]["dob"] == "1950-09-10"

    match, records = voter_file.match_node(
        "CURRIE, HENRY", {"date_of_birth": "1950-09-10"}, set(), index
    )
    assert match == voter_file.MATCH_DOB

    match, _ = voter_file.match_node("SMITH, JOHN", {}, set(), index)
    assert match == voter_file.MATCH_NONE


def test_enrich_graph_sets_dob_and_match_type(tmp_path):
    path = tmp_path / "voters.csv"
    _voter_csv(
        path,
        [
            {
                "SOS_VOTERID": "OH1",
                "LAST_NAME": "CURRIE",
                "FIRST_NAME": "HENRY",
                "MIDDLE_NAME": "",
                "DATE_OF_BIRTH": "09/10/1950",
                "VOTER_STATUS": "ACTIVE",
                "PARTY_AFFILIATION": "D",
                "RESIDENTIAL_ADDRESS1": "1 MAIN ST",
                "RESIDENTIAL_CITY": "CLEVELAND",
                "RESIDENTIAL_ZIP": "44102",
            }
        ],
    )
    index = voter_file.build_voter_index(path)
    graph = nx.Graph()
    graph.add_node(
        "owner|CURRIE, HENRY",
        type="owner",
        kind="person",
        name="CURRIE, HENRY",
    )
    stats = voter_file.enrich_graph(graph, index)
    assert stats["unique"] == 1
    assert graph.nodes["owner|CURRIE, HENRY"]["voter_match"] == voter_file.MATCH_NAME_UNIQUE
    assert graph.nodes["owner|CURRIE, HENRY"]["date_of_birth"] == "1950-09-10"


def test_legacy_marriage_pipeline_accepts_new_match_vocabulary():
    from osi.loaders import marriage

    assert marriage._voter_matched({"voter_match": "name_unique"})
    assert marriage._voter_matched({"voter_match": "dob"})
    assert marriage._voter_matched({"voter_match": "address"})
    assert not marriage._voter_matched({"voter_match": "ambiguous"})
    assert not marriage._voter_matched({"voter_match": "unique"})
