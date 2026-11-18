"""Regression tests for Cuyahoga parcel, transfer, and resume behavior."""

from __future__ import annotations

import json
from pathlib import Path

from osi.loaders import cuyahoga, cuyahoga_transfers
from osi.loaders.io_utils import resume_targets


def _write_csv(path: Path) -> None:
    # ArcGIS CSV exports include a UTF-8 BOM before the first header.
    text = (
        "\ufeffparcel_id,parcel_owner,parcelpin,account,property_class,"
        "par_addr_all,parcel_city,parcel_zip,tax_market_total,"
        "mail_addr_street,mail_city,mail_zip\n"
        "00101012,JOHN SMITH,123,456,R,11524 EDGEWATER DR,CLEVELAND,44102,"
        "125000,1 MAIN ST,CLEVELAND,44101\n"
    )
    path.write_text(text, encoding="utf-8")


def test_csv_bom_is_stripped_and_schema_aliases_are_written(tmp_path):
    path = tmp_path / "parcels.csv"
    _write_csv(path)
    graph, meta = cuyahoga.load_cuyahoga_parcels(path)

    assert meta["rows_read"] == 1
    assert meta["rows_kept"] == 1
    parcel = graph.nodes["parcel|00101012"]
    assert parcel["situs"] == "11524 EDGEWATER DR, CLEVELAND, OH, 44102"
    assert parcel["situs_addr"] == "11524 EDGEWATER DR"
    assert parcel["situs_zip"] == "44102"
    assert parcel["value"] == 125000.0
    assert parcel["tax_market_total"] == 125000.0
    assert graph.has_edge("owner|JOHN SMITH", "parcel|00101012")


def test_format_detection_reads_only_the_first_row(tmp_path):
    path = tmp_path / "parcels.csv"
    _write_csv(path)
    assert cuyahoga.detect_cuyahoga_format(path) == "high"


def test_transfer_parties_preserve_corporate_names():
    assert cuyahoga_transfers.transfer_parties("SMITH AND JONES LLC") == [
        "SMITH AND JONES LLC"
    ]
    assert cuyahoga_transfers.transfer_parties("BLUE CROSS & BLUE SHIELD") == [
        "BLUE CROSS & BLUE SHIELD"
    ]
    assert cuyahoga_transfers.transfer_parties("JOHN SMITH & JANE ROE") == [
        "JOHN SMITH",
        "JANE ROE",
    ]
    assert cuyahoga_transfers.transfer_parties("SMITH, JOHN, TRUSTEE") == [
        "SMITH, JOHN"
    ]
    assert cuyahoga_transfers.transfer_parties("SEE PARCEL 123") == []
    assert cuyahoga_transfers.transfer_parties("UNKNOWN") == []


def test_transfer_graph_does_not_split_corporate_grantors():
    graph, _ = cuyahoga_transfers.build_transfer_graph(
        [
            {
                "grantor": "SMITH AND JONES LLC",
                "grantee": "JANE ROE",
                "last_transfer_date": 0,
                "last_sales_amount": "1000",
            }
        ]
    )
    assert set(graph.nodes) == {"owner|SMITH AND JONES LLC", "owner|JANE ROE"}
    assert graph.has_edge("owner|SMITH AND JONES LLC", "owner|JANE ROE")


def test_module_import_has_no_side_effects(tmp_path, monkeypatch):
    # Importing must not read the default raw export or write a pickle.
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())
    import osi.loaders.cuyahoga_transfers  # noqa: F401
    assert set(tmp_path.iterdir()) == before


def _records(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def test_resume_targets_retries_empty_success_and_no_results(tmp_path):
    records = [
        {"node_key": "a", "status": "success", "rows": [{"name": "A"}]},
        {"node_key": "b", "status": "success", "rows": []},
        {"node_key": "c", "status": "no_results", "rows": []},
        {"node_key": "d", "status": "error"},
    ]
    targets = [{"node_key": key} for key in "abcd"]
    pending = resume_targets(
        targets,
        records,
        has_evidence=lambda record: bool(record.get("rows")),
        empty_statuses={"no_results"},
        max_empty_attempts=2,
    )
    assert {row["node_key"] for row in pending} == {"b", "c", "d"}

    records.append({"node_key": "b", "status": "no_results", "rows": []})
    records.append({"node_key": "c", "status": "no_results", "rows": []})
    pending = resume_targets(
        targets,
        records,
        has_evidence=lambda record: bool(record.get("rows")),
        empty_statuses={"no_results"},
        max_empty_attempts=2,
    )
    assert {row["node_key"] for row in pending} == {"d"}


def test_courts_load_targets_treats_legacy_empty_success_as_retry(tmp_path):
    from osi.loaders import courts_background

    targets_path = tmp_path / "targets.json"
    progress_path = tmp_path / "progress.jsonl"
    targets_path.write_text(
        json.dumps([{"node_key": "a", "last": "A", "first": "A"}]), encoding="utf-8"
    )
    _records(progress_path, [{"node_key": "a", "status": "success", "rows": []}])

    assert courts_background.load_targets(targets_path, progress_path) == [
        {"node_key": "a", "last": "A", "first": "A"}
    ]


def test_marriage_verified_pair_rejects_unrelated_cases():
    from osi.loaders import marriage_background

    assert marriage_background.verified_pair(
        ["HENRY CURRIE JR", "MARY JONES"], "CURRIE", "HENRY"
    ) == ["HENRY CURRIE JR", "MARY JONES"]
    assert (
        marriage_background.verified_pair(
            ["ALICE BROWN", "BOB GREEN"], "CURRIE", "HENRY"
        )
        is None
    )
    assert marriage_background.verified_pair(["HENRY CURRIE JR"], "CURRIE", "HENRY") is None


def test_marriage_load_targets_retries_unverified(tmp_path):
    from osi.loaders import marriage_background

    targets_path = tmp_path / "targets.json"
    progress_path = tmp_path / "progress.jsonl"
    targets_path.write_text(
        json.dumps([{"node_key": "a", "last": "A", "first": "A"}]), encoding="utf-8"
    )
    _records(
        progress_path,
        [{"node_key": "a", "status": "unverified", "parties": []}],
    )
    assert marriage_background.load_targets(targets_path, progress_path) == [
        {"node_key": "a", "last": "A", "first": "A"}
    ]
    _records(
        progress_path,
        [
            {"node_key": "a", "status": "unverified", "parties": []},
            {"node_key": "a", "status": "unverified", "parties": []},
        ],
    )
    assert marriage_background.load_targets(targets_path, progress_path) == []


def test_merge_derive_reads_both_schema_variants(tmp_path):
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "analysis" / "cuyahoga" / "merge_derive.py"
    spec = importlib.util.spec_from_file_location("merge_derive", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.situs_zip("11524 EDGEWATER DR, CLEVELAND, OH, 44102") == "44102"
    assert module.situs_zip("44103") == "44103"
    assert module.parcel_value({"value": "12.5"}) == 12.5
    assert module.parcel_value({"tax_market_total": 20}) == 20.0
    assert module.classify("JOHN SMITH") == "person"
    assert module.classify("SMITH AND JONES LLC") == "entity"
