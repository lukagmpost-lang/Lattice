"""Build a grantor-grantee transfer graph from a Cuyahoga transfer export.

The module is import-safe: nothing runs until ``main()``.  Party splitting uses
the shared :mod:`osi.names` parser so a corporate name such as
``SMITH AND JONES LLC`` is not cut into two owners.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

from osi.loaders.io_utils import atomic_pickle_dump
from osi.names import clean_name, is_placeholder, split_parties

_DEFAULT_RAW = Path(os.path.expanduser("~/Desktop/cuyahoga_transfers_raw.json"))
_DEFAULT_OUT = Path(os.path.expanduser("~/Desktop/cuyahoga_transfers.pkl"))
_DEFAULT_OWNERSHIP = Path(os.path.expanduser("~/Desktop/cuyahoga_graph.pkl"))


def _u(value) -> str:
    return clean_name(value).upper()


def _n(value) -> str:
    return clean_name(value)


def transfer_parties(value) -> list[str]:
    """Split a grantor/grantee field without breaking corporate names."""
    text = clean_name(value)
    if not text or is_placeholder(text) or text.upper().startswith("SEE PARCEL"):
        return []
    parties = []
    for party in split_parties(text):
        party = clean_name(party)
        if party and not is_placeholder(party):
            parties.append(party.upper())
    return list(dict.fromkeys(parties))


def _date(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d"
        )
    except (TypeError, ValueError, OverflowError):
        return None


def _float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def load_rows(path: str | Path) -> list[dict]:
    path = Path(path)
    with path.open(encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return [
        feature.get("attributes", {})
        for feature in data.get("features", [])
    ]


def build_transfer_graph(rows: list[dict]) -> tuple[nx.DiGraph, list[tuple[str, list[str]]]]:
    graph = nx.DiGraph()
    amp_examples: list[tuple[str, list[str]]] = []
    for row in rows:
        grantors = transfer_parties(row.get("grantor"))
        grantees = transfer_parties(row.get("grantee"))
        if not grantors or not grantees:
            continue
        date = _date(row.get("last_transfer_date"))
        amount = _float(row.get("last_sales_amount"))
        book_page = _n(row.get("book_page")) or None
        raw_grantor = str(row.get("grantor") or "")
        if "&" in raw_grantor and len(amp_examples) < 8 and len(grantors) > 1:
            amp_examples.append((raw_grantor, grantors))
        for grantor in grantors:
            for grantee in grantees:
                if grantor == grantee:
                    continue
                gk, tk = f"owner|{grantor}", f"owner|{grantee}"
                if graph.has_edge(gk, tk):
                    edge = graph[gk][tk]
                    edge["weight"] += 1
                    if amount:
                        edge["total_amount"] += amount
                    if date:
                        if not edge.get("first_date") or date < edge["first_date"]:
                            edge["first_date"] = date
                        if not edge.get("last_date") or date > edge["last_date"]:
                            edge["last_date"] = date
                    if book_page:
                        edge["book_pages"].append(book_page)
                else:
                    graph.add_edge(
                        gk,
                        tk,
                        weight=1,
                        total_amount=amount or 0.0,
                        first_date=date,
                        last_date=date,
                        book_pages=[book_page] if book_page else [],
                        relation="transfer",
                    )
    return graph, amp_examples


def overlap_with_ownership(graph: nx.DiGraph, ownership_path: str | Path) -> dict:
    ownership_path = Path(ownership_path)
    if not ownership_path.exists():
        return {"available": False}
    with ownership_path.open("rb") as handle:
        existing = pickle.load(handle)
    existing_owners = {
        str(node)[6:]
        for node in existing.nodes
        if str(node).startswith("owner|")
    }
    grantors = {node for node, _ in graph.out_degree}
    grantees = {node for _, node in graph.in_degree}
    transfer_names = {node[6:] for node in grantors | grantees}
    overlap = transfer_names & existing_owners
    return {
        "available": True,
        "grantors": len(grantors),
        "grantees": len(grantees),
        "transfer_nodes": len(grantors | grantees),
        "overlap": len(overlap),
        "overlap_pct": 100 * len(overlap) / max(1, len(transfer_names)),
    }


def _print_report(graph: nx.DiGraph, amp_examples: list, overlap: dict) -> None:
    print("=" * 72)
    print("1. NODE COUNT & OVERLAP")
    print(f"   transfer nodes: {graph.number_of_nodes():,}")
    if overlap.get("available"):
        print(
            f"   overlap with existing owners: {overlap['overlap']:,} "
            f"({overlap['overlap_pct']:.1f}%)"
        )
    print("\n2. & SPLIT PROOF")
    for index, (raw, parts) in enumerate(amp_examples[:5], 1):
        print(f"   [{index}] RAW: {raw[:80]}")
        for part in parts:
            print(f"        -> owner|{part}")
    weights = [data["weight"] for _, _, data in graph.edges(data=True)]
    repeated = sum(1 for weight in weights if weight > 1)
    print("\n3. EDGE WEIGHT DISTRIBUTION")
    print(f"   edges:       {len(weights):,}")
    if weights:
        print(f"   weight >1:   {repeated:,} ({100 * repeated / len(weights):.1f}%)")
        print(f"   max weight:  {max(weights):,}")


def main(
    *,
    raw_path: str | Path = _DEFAULT_RAW,
    out_path: str | Path = _DEFAULT_OUT,
    ownership_path: str | Path = _DEFAULT_OWNERSHIP,
) -> nx.DiGraph:
    rows = load_rows(raw_path)
    print(f"loaded {len(rows):,} rows")
    graph, amp_examples = build_transfer_graph(rows)
    overlap = overlap_with_ownership(graph, ownership_path)
    _print_report(graph, amp_examples, overlap)
    atomic_pickle_dump(graph, out_path)
    print(f"\nwrote {out_path}: {graph.number_of_nodes():,} nodes, "
          f"{graph.number_of_edges():,} edges")
    return graph


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default=str(_DEFAULT_RAW))
    parser.add_argument("--out", default=str(_DEFAULT_OUT))
    parser.add_argument("--ownership", default=str(_DEFAULT_OWNERSHIP))
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    main(raw_path=args.raw, out_path=args.out, ownership_path=args.ownership)
