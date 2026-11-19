"""Tests for the derived persons_enriched.parquet builder."""

from __future__ import annotations

import pickle
from pathlib import Path

import networkx as nx

from analysis.cuyahoga import build_persons_enriched as builder


def test_extract_zip_uses_last_five_digit_group():
    assert builder.extract_zip("123 MAIN ST, CLEVELAND, 44102-1234") == "44102"
    assert builder.extract_zip("44115") == "44115"
    assert builder.extract_zip("") == ""


def test_normalize_source_name_moves_suffix_after_last_name():
    name, suffix = builder.normalize_source_name("SMITH, SR., RONALD O.")
    assert name == "SMITH, RONALD O."
    assert suffix == "SR"

    name, suffix = builder.normalize_source_name("MILLER, JENNIFER, ANN")
    assert name == "MILLER, JENNIFER ANN"
    assert suffix == ""


def test_valid_name_part_accepts_initials_and_rejects_placeholders():
    assert builder.valid_name_part("A.")
    assert builder.valid_name_part("O'CONNOR")
    assert builder.valid_name_part("SMITH-JONES")
    assert not builder.valid_name_part("#1")
    assert not builder.valid_name_part("&ASSOC")
    assert not builder.valid_name_part("")


def test_build_rows_filters_organizations_and_bad_names(tmp_path: Path):
    graph = nx.DiGraph()
    graph.add_node(
        "owner|SMITH, JOHN A",
        type="owner",
        kind="person",
        name="SMITH, JOHN A",
        date_of_birth="1980-01-01",
        residential_address="123 MAIN ST, CLEVELAND, 44102",
        top_zip="44102",
        voter_id="OH0001",
    )
    graph.add_node(
        "owner|ACME LLC",
        type="owner",
        kind="person",
        name="ACME LLC",
    )
    graph.add_node(
        "owner|, MISSING FIRST",
        type="owner",
        kind="person",
        name=", MISSING FIRST",
    )
    graph.add_node(
        "parcel|123",
        type="parcel",
        name="123 MAIN ST",
    )

    path = tmp_path / "graph.pkl"
    with path.open("wb") as handle:
        pickle.dump(graph, handle)

    rows, stats = builder.build_rows(path)

    assert stats["person_nodes"] == 3
    assert stats["parsed"] == 1
    assert len(rows) == 1
    row = rows[0]
    assert row["node_id"] == "owner|SMITH, JOHN A"
    assert row["first_name"] == "JOHN"
    assert row["last_name"] == "SMITH"
    assert row["middle_initial"] == "A"
    assert row["dob"] == "1980-01-01"
    assert row["zip_code"] == "44102"
    assert row["voter_id"] == "OH0001"
    assert row["full_name"] == "JOHN SMITH"
