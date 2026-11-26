"""Regression tests for the strict parcel-transfer network."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

import build_parcel_transfer_network as parcel


def _cluster_frame() -> pd.DataFrame:
    rows = [
        ("owner|A1", 10, "HIGH", "ALICE A"),
        ("owner|A2", 10, "HIGH", "ALICE A"),
        ("owner|B1", 20, "HIGH", "BOB B"),
        ("owner|C1", 30, "LOW", "CAROL C"),
        ("owner|D1", 40, "HIGH", "DAN D"),
    ]
    return pd.DataFrame(
        rows,
        columns=["node_id", "cluster_id", "confidence_level", "full_name"],
    )


def _row(parcel_id: str, grantor: str, grantee: str, amount: float) -> dict:
    return {
        "parcel_id": parcel_id,
        "grantor": grantor,
        "grantee": grantee,
        "last_transfer_date": 0,
        "last_sales_amount": amount,
        # Deliberately reused across parcels and transactions.
        "book_page": "B 1 P 1",
    }


def test_joint_deeds_repeated_parcels_and_strict_filters():
    rows = [
        # Two distinct HIGH grantor clusters: two associations, one deed.
        _row("P1", "A1 & D1", "B1", 60_000),
        # Aliases collapse to one grantor cluster on a second P1 deed.
        _row("P1", "A1 & A2", "B1", 70_000),
        # The same book/page on another parcel must not overwrite anything.
        _row("P2", "A1", "B1", 80_000),
        _row("P3", "A1", "B1", 50_000),  # Strictly greater is required.
        _row("P4", "A1", "C1", 90_000),  # Only one HIGH endpoint.
        _row("P5", "A1", "A2", 90_000),  # Same resolved entity.
        _row("P6", "UNKNOWN PERSON", "B1", 90_000),
    ]
    index = parcel.build_cluster_index(_cluster_frame())

    associations, stats = parcel.analyze_transactions(rows, index)
    graph = parcel.build_graph(associations, index, {"P1": "1 MAIN ST"})
    ranking = parcel.rank_parcels(associations, {"P1": "1 MAIN ST"})

    assert stats["raw_rows"] == 7
    assert stats["amount_eligible_rows"] == 6
    assert stats["rows_with_cross_entity_pair"] == 4
    assert stats["rows_with_both_high_pair"] == 3
    assert stats["both_high_transaction_cluster_pairs"] == 4
    assert stats["both_high_parcels"] == 2
    assert stats["unresolved_grantor_parties"] == 1
    assert graph.number_of_edges() == 8  # Four associations, two half-edges each.
    assert all(
        data["conf_a"] == "HIGH" and data["conf_b"] == "HIGH"
        for _, _, _, data in graph.edges(keys=True, data=True)
    )

    p1 = ranking.set_index("parcel_id").loc["P1"]
    assert p1["observed_transfer_count"] == 2
    assert p1["distinct_cluster_pairs"] == 2
    assert p1["distinct_clusters"] == 3
    assert p1["total_volume"] == 130_000
    assert p1["avg_amount"] == 65_000
    assert len(p1["transaction_ids"].split(";")) == 2
    assert ranking.iloc[0]["parcel_id"] == "P1"


def test_no_both_high_transactions_produces_empty_typed_outputs():
    index = parcel.build_cluster_index(_cluster_frame())
    rows = [_row("P1", "A1", "C1", 100_000)]

    associations, stats = parcel.analyze_transactions(rows, index)
    graph = parcel.build_graph(associations, index, {})
    ranking = parcel.rank_parcels(associations, {})

    assert associations == []
    assert stats["rows_with_cross_entity_pair"] == 1
    assert stats["rows_with_both_high_pair"] == 0
    assert graph.number_of_nodes() == 0
    assert list(ranking.columns) == parcel.RANKING_COLUMNS
    assert ranking.empty


def test_cluster_schema_and_confidence_are_validated():
    frame = _cluster_frame()
    frame.loc[1, "confidence_level"] = "LOW"
    with pytest.raises(ValueError, match="inconsistent confidence"):
        parcel.build_cluster_index(frame)

    with pytest.raises(ValueError, match="missing columns"):
        parcel.build_cluster_index(frame.drop(columns=["full_name"]))

    invalid = _cluster_frame()
    invalid.loc[0, "confidence_level"] = "UNKNOWN"
    with pytest.raises(ValueError, match="invalid confidence_level"):
        parcel.build_cluster_index(invalid)


def test_no_data_png_is_explicit(tmp_path: Path):
    path = tmp_path / "empty.png"
    parcel.render_png(nx.MultiDiGraph(), path, dpi=20)

    assert path.read_bytes().startswith(b"\x89PNG")


def test_help_does_not_require_production_inputs(tmp_path: Path):
    script = Path(parcel.__file__).resolve()
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-B", str(script), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "last-transfer snapshot" in result.stdout
    assert list(tmp_path.iterdir()) == []
