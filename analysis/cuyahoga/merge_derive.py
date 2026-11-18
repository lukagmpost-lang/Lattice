"""Merge ownership, transfer, and derived attributes into the unified graph.

Run with ``PYTHONPATH=src python analysis/cuyahoga/merge_derive.py``.  The
script now reads both the canonical parcel attributes (``situs``/``value``)
and the older split fields, and writes the unified pickle atomically.
"""

from __future__ import annotations

import argparse
import os
import pickle
import re
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import networkx as nx

from osi.loaders.io_utils import atomic_pickle_dump, backup_file
from osi.names import is_organization, person_identity

_DEFAULT_OWNERSHIP = Path(os.path.expanduser("~/Desktop/cuyahoga_graph.pkl"))
_DEFAULT_TRANSFERS = Path(os.path.expanduser("~/Desktop/cuyahoga_transfers.pkl"))
_DEFAULT_OUT = Path(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"))


def _u(value) -> str:
    return "" if value is None else re.sub(r"\s+", " ", str(value)).strip().upper()


def classify(name: str) -> str:
    """Classify an owner string as person, entity, or unknown."""
    text = _u(name)
    if not text:
        return "unknown"
    if is_organization(text):
        return "entity"
    if person_identity(text) is not None:
        return "person"
    return "unknown"


def situs_zip(value) -> str:
    """Extract a five-digit ZIP from ``situs`` or a split situs field."""
    text = _u(value)
    if not text:
        return ""
    matches = re.findall(r"\b(\d{5})(?:-\d{4})?\b", text)
    if matches:
        # An address starts with a street number; the ZIP is the last group.
        return matches[-1]
    parts = text.rsplit(",", 1)
    return parts[-1].strip() if len(parts) == 2 else ""


def parcel_value(data: dict) -> float:
    for key in ("value", "tax_market_total", "last_sales_amount"):
        try:
            value = data.get(key)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def enrich_owners(graph: nx.Graph) -> dict[str, int]:
    """Add derived ownership attributes to every ``owner|`` node."""
    counts = Counter()
    for owner in [node for node in graph.nodes if str(node).startswith("owner|")]:
        kind = classify(str(owner)[6:])
        parcels = [
            node
            for node in graph.neighbors(owner)
            if graph.nodes[node].get("type") == "parcel"
        ]
        zips = Counter(
            situs_zip(
                graph.nodes[node].get("situs")
                or graph.nodes[node].get("situs_zip")
            )
            for node in parcels
        )
        zips.pop("", None)
        addresses = sum(
            1
            for node in graph.neighbors(owner)
            if graph.nodes[node].get("type") == "address"
        )
        data = graph.nodes[owner]
        data["kind"] = kind
        data["total_parcels"] = len(parcels)
        data["total_value"] = sum(parcel_value(graph.nodes[node]) for node in parcels)
        data["n_addresses"] = addresses
        data["n_zips"] = len(zips)
        data["top_zip"] = zips.most_common(1)[0][0] if zips else None
        counts[kind] += 1
    return dict(counts)


def add_same_mail_edges(graph: nx.Graph, cap: int = 15) -> int:
    added = 0
    for address, data in graph.nodes(data=True):
        if data.get("type") != "address":
            continue
        owners = [
            node
            for node in graph.neighbors(address)
            if graph.nodes[node].get("type") == "owner"
        ]
        if not (2 <= len(owners) <= cap):
            continue
        for i, left in enumerate(owners):
            for right in owners[i + 1 :]:
                if graph.has_edge(left, right):
                    graph[left][right].setdefault("mail_count", 0)
                    graph[left][right]["mail_count"] += 1
                else:
                    graph.add_edge(
                        left, right, relation="same_mail", mail_count=1
                    )
                    added += 1
    return added


def add_transfer_edges(graph: nx.Graph, transfers: nx.DiGraph) -> int:
    added = 0
    incoming: Counter[str] = Counter()
    outgoing: Counter[str] = Counter()
    for source, target, data in transfers.edges(data=True):
        weight = data.get("weight", 1)
        outgoing[source] += weight
        incoming[target] += weight
        if source in graph and target in graph:
            if graph.has_edge(source, target):
                graph[source][target].setdefault("tx_weight", 0)
                graph[source][target]["tx_weight"] += weight
            else:
                graph.add_edge(source, target, relation="sold_to", tx_weight=weight)
                added += 1
    for node in graph.nodes:
        if str(node).startswith("owner|"):
            graph.nodes[node]["transfer_in"] = incoming.get(node, 0)
            graph.nodes[node]["transfer_out"] = outgoing.get(node, 0)
    return added


def merge(
    ownership_path: str | Path = _DEFAULT_OWNERSHIP,
    transfers_path: str | Path = _DEFAULT_TRANSFERS,
    out_path: str | Path = _DEFAULT_OUT,
    *,
    apply: bool = True,
) -> nx.Graph:
    ownership_path = Path(ownership_path)
    transfers_path = Path(transfers_path)
    with ownership_path.open("rb") as handle:
        graph = pickle.load(handle)
    with transfers_path.open("rb") as handle:
        transfers = pickle.load(handle)
    print(
        f"  ownership: {graph.number_of_nodes():,} nodes, "
        f"{graph.number_of_edges():,} edges"
    )
    print(
        f"  transfers: {transfers.number_of_nodes():,} nodes, "
        f"{transfers.number_of_edges():,} edges"
    )

    print("\nclassifying owners...")
    counts = enrich_owners(graph)
    for kind in ("person", "entity", "unknown"):
        print(f"  {kind}: {counts.get(kind, 0):,}")

    print("\nadding same_mail edges (group capped at 15)...")
    print(f"  added {add_same_mail_edges(graph):,} same_mail edges")

    print("\nadding transfer edges and counterpart attributes...")
    print(f"  added {add_transfer_edges(graph, transfers):,} sold_to edges")

    if apply:
        out_path = Path(out_path)
        if out_path.exists():
            backup = backup_file(out_path)
            print(f"  backup: {backup}")
        atomic_pickle_dump(graph, out_path)
        print(
            f"\nwrote {out_path}: {graph.number_of_nodes():,} nodes, "
            f"{graph.number_of_edges():,} edges"
        )
    return graph


def _print_rankings(graph: nx.Graph) -> None:
    print("\nTOP 15 PERSONS by parcels")
    persons = [
        (node, graph.nodes[node])
        for node in graph.nodes
        if graph.nodes[node].get("kind") == "person"
    ]
    persons.sort(key=lambda item: -item[1].get("total_parcels", 0))
    for node, data in persons[:15]:
        print(
            f"  {data.get('total_parcels', 0):4d}p  "
            f"{data.get('transfer_in', 0):4d}in "
            f"{data.get('transfer_out', 0):4d}out  {str(node)[6:][:60]}"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ownership", default=str(_DEFAULT_OWNERSHIP))
    parser.add_argument("--transfers", default=str(_DEFAULT_TRANSFERS))
    parser.add_argument("--out", default=str(_DEFAULT_OUT))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    graph = merge(
        args.ownership,
        args.transfers,
        args.out,
        apply=not args.dry_run,
    )
    _print_rankings(graph)


if __name__ == "__main__":
    main()
