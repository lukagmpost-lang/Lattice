#!/usr/bin/env python3
"""Build the Splink input table from the unified Cuyahoga graph.

The production ``persons_enriched.parquet`` referenced in the pipeline plan was
never present in the repository.  The unified ownership graph already contains
the person-owner nodes plus the voter-file fields the Splink model needs, so
this script flattens those nodes into the canonical schema.

Output columns:
    node_id, first_name, last_name, middle_initial, suffix, dob, address,
    zip_code, voter_id, full_name, source_name

Run:
    .venv/bin/python analysis/cuyahoga/build_persons_enriched.py
"""

from __future__ import annotations

import argparse
import pickle
import re
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from osi.names import is_organization, parse_date_of_birth, parse_person  # noqa: E402

_DEFAULT_GRAPH = Path.home() / "Desktop" / "cuyahoga_unified.pkl"
_DEFAULT_OUT = _ROOT / "analysis" / "cuyahoga" / "data" / "persons_enriched.parquet"

_COLUMNS = [
    "node_id",
    "first_name",
    "last_name",
    "middle_initial",
    "suffix",
    "dob",
    "address",
    "zip_code",
    "voter_id",
    "full_name",
    "source_name",
]


def extract_zip(value: object) -> str:
    """Return the last five-digit ZIP found in an address or ZIP field."""
    text = "" if value is None else str(value).strip().upper()
    matches = re.findall(r"\b(\d{5})(?:-\d{4})?\b", text)
    return matches[-1] if matches else ""


_NAME_RE = re.compile(r"[A-Z][A-Z .'’\-]*")
_SUFFIX_AFTER_LAST_RE = re.compile(
    r"^([^,]+),\s*(JR|SR|II|III|IV|V)\.?\s*,\s*(.+)$"
)


def normalize_source_name(value: object) -> tuple[str, str]:
    """Return ``(name_for_parser, suffix)`` for the forms in this dataset.

    A handful of names put the generational suffix immediately after the
    surname (``SMITH, SR., RONALD O.``).  ``parse_person`` expects the suffix at
    the end, so move it there before parsing.
    """
    text = str(value or "").strip().upper()
    match = _SUFFIX_AFTER_LAST_RE.match(text)
    if match:
        text = f"{match.group(1).strip()}, {match.group(3).strip()}"
        suffix = match.group(2)
    else:
        suffix = ""

    # Extra commas/colons in the given-name portion (``MILLER, JENNIFER, ANN``)
    # are separators, not part of the name.  Normalise them to spaces after the
    # first comma so the first token remains the forename.
    if "," in text:
        last, rest = text.split(",", 1)
        rest = re.sub(r"[,:;]", " ", rest)
        text = f"{last}, {rest}"
    return re.sub(r"\s+", " ", text).strip(), suffix


def valid_name_part(value: str) -> bool:
    """Reject placeholders such as ``#1`` and obvious non-names.

    Single-letter initials (``J``, ``A.``) are valid.  Names may contain
    spaces, periods, apostrophes, and hyphens, but not digits or address-style
    punctuation such as ``#``, ``&``, ``(``, ``)``, ``,``, or ``/``.
    """
    return bool(_NAME_RE.fullmatch(value))


def build_rows(graph_path: Path, *, limit: int | None = None) -> tuple[list[dict], dict]:
    with graph_path.open("rb") as handle:
        graph = pickle.load(handle)

    stats = {
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "person_nodes": 0,
        "parsed": 0,
        "skipped": 0,
        "skipped_org": 0,
        "skipped_quality": 0,
        "skipped_punctuation": 0,
        "with_dob": 0,
        "with_address": 0,
        "with_voter_id": 0,
        "with_zip": 0,
    }
    skipped_examples: list[str] = []
    rows: list[dict] = []

    for node, data in graph.nodes(data=True):
        if data.get("type") != "owner" or data.get("kind") != "person":
            continue
        stats["person_nodes"] += 1

        source_name = str(data.get("name") or "").strip().upper()
        if not source_name or not source_name[0].isalpha():
            stats["skipped_punctuation"] += 1
            continue

        if is_organization(source_name):
            stats["skipped_org"] += 1
            continue

        parse_name, suffix_hint = normalize_source_name(source_name)
        parsed = parse_person(parse_name)
        if parsed is None:
            stats["skipped"] += 1
            if len(skipped_examples) < 10:
                skipped_examples.append(source_name)
            continue

        last, first, middle, suffix = parsed
        suffix = suffix or suffix_hint
        if not valid_name_part(last) or not valid_name_part(first):
            stats["skipped_quality"] += 1
            if len(skipped_examples) < 10:
                skipped_examples.append(source_name)
            continue
        # Two initials are not enough to identify a person.
        if len(first.replace(".", "")) <= 1 and len(last.replace(".", "")) <= 1:
            stats["skipped_quality"] += 1
            continue

        # Middle names in the source contain commas, periods, and stray
        # tokens.  Keep only letters so the initial is meaningful.
        middle_clean = re.sub(r"[^A-Z]", " ", middle).strip()
        middle_initial = next(
            (char for char in middle_clean if char.isalpha()), ""
        )

        dob = parse_date_of_birth(data.get("date_of_birth"))
        address = str(data.get("residential_address") or "").strip().upper()
        zip_code = extract_zip(data.get("top_zip")) or extract_zip(address)
        voter_id = str(data.get("voter_id") or "").strip().upper()

        rows.append(
            {
                "node_id": str(node),
                "first_name": first,
                "last_name": last,
                "middle_initial": middle_initial,
                "suffix": (suffix or "").upper(),
                "dob": dob.isoformat() if dob else "",
                "address": address,
                "zip_code": zip_code,
                "voter_id": voter_id,
                "full_name": f"{first} {last}".strip(),
                "source_name": source_name,
            }
        )
        stats["parsed"] += 1
        stats["with_dob"] += bool(dob)
        stats["with_address"] += bool(address)
        stats["with_voter_id"] += bool(voter_id)
        stats["with_zip"] += bool(zip_code)

        if limit is not None and len(rows) >= limit:
            break

    # Deterministic ordering makes unique_id assignment reproducible across
    # runs and machines.
    rows.sort(key=lambda row: row["node_id"])
    stats["skipped_examples"] = skipped_examples
    return rows, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default=str(_DEFAULT_GRAPH))
    parser.add_argument("--out", default=str(_DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    graph_path = Path(args.graph).expanduser()
    if not graph_path.exists():
        parser.error(f"graph not found: {graph_path}")

    rows, stats = build_rows(graph_path, limit=args.limit)
    print("Input graph:", graph_path)
    print(f"  graph: {stats['graph_nodes']:,} nodes / {stats['graph_edges']:,} edges")
    print(f"  person owner nodes: {stats['person_nodes']:,}")
    print(f"  parsed: {stats['parsed']:,}")
    print(f"  skipped (organization): {stats['skipped_org']:,}")
    print(f"  skipped (unparseable name): {stats['skipped']:,}")
    print(f"  skipped (placeholder/non-name): {stats['skipped_quality']:,}")
    print(f"  skipped (leading punctuation): {stats['skipped_punctuation']:,}")
    print(f"  with DOB: {stats['with_dob']:,}")
    print(f"  with address: {stats['with_address']:,}")
    print(f"  with ZIP: {stats['with_zip']:,}")
    print(f"  with voter ID: {stats['with_voter_id']:,}")
    if stats["skipped_examples"]:
        print("  skipped examples:", stats["skipped_examples"])

    if not rows:
        print("No parseable person rows; nothing to write.")
        return 1

    df = pd.DataFrame(rows, columns=_COLUMNS)
    print("\nResult frame:", df.shape)
    print(df.head(5).to_string(index=False))

    if args.dry_run:
        print("\nDry run: no file written.")
        return 0

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False, compression="zstd")
    print(f"\nWrote {out} ({out.stat().st_size / 1_000_000:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
