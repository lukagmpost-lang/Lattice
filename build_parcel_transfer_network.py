#!/usr/bin/env python3
"""Build a provenance-preserving Cluster -> Parcel -> Cluster network.

The current Cuyahoga export is a last-transfer snapshot, not deed history.
The CSV therefore ranks observed cross-entity source transactions; it is not a
historical property-flip ranking.  Qualifying transactions have a row-level
amount strictly greater than $50,000 and HIGH confidence at both endpoints.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from osi.loaders.cuyahoga_transfers import (  # noqa: E402
    iter_transfer_transactions,
    load_rows,
)

DEFAULT_RAW = Path.home() / "Desktop" / "cuyahoga_transfers_raw.json"
DEFAULT_CLUSTERS = _ROOT / "cuyahoga_resolved_clusters.parquet"
DEFAULT_UNIFIED = Path.home() / "Desktop" / "cuyahoga_unified.pkl"

RANKING_COLUMNS = [
    "parcel_id",
    "situs",
    "observed_transfer_count",
    "distinct_clusters",
    "distinct_cluster_pairs",
    "total_volume",
    "avg_amount",
    "first_transfer_date",
    "last_transfer_date",
    "transaction_ids",
    "clusters",
]


def normalize_name(value: object) -> str:
    """Normalize owner-node keys without losing the owner namespace."""
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def build_cluster_index(frame: pd.DataFrame) -> dict:
    """Validate resolved-cluster data and construct deterministic lookups."""
    required = {"node_id", "cluster_id", "confidence_level", "full_name"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"cluster parquet missing columns: {sorted(missing)}")

    if frame[["node_id", "cluster_id"]].isna().any().any():
        raise ValueError("node_id and cluster_id must not be null")
    invalid_confidence = ~frame["confidence_level"].isin(["HIGH", "LOW"])
    if invalid_confidence.any():
        values = sorted(
            frame.loc[invalid_confidence, "confidence_level"].astype(str).unique()
        )
        raise ValueError(f"invalid confidence_level values: {values}")

    owner_to_cluster: dict[str, str] = {}
    for node_id, cluster_id in zip(frame["node_id"], frame["cluster_id"]):
        key = normalize_name(node_id)
        cluster = str(cluster_id)
        if not key or not cluster:
            raise ValueError("blank node_id or cluster_id in cluster parquet")
        previous = owner_to_cluster.get(key)
        if previous is not None and previous != cluster:
            raise ValueError(f"normalized owner maps to multiple clusters: {key}")
        owner_to_cluster[key] = cluster

    rows = frame.copy()
    rows["cluster_id"] = rows["cluster_id"].astype(str)
    confidence_counts = rows.groupby("cluster_id")["confidence_level"].nunique()
    inconsistent = confidence_counts[confidence_counts > 1]
    if not inconsistent.empty:
        raise ValueError(
            "clusters have inconsistent confidence levels: "
            + ", ".join(inconsistent.index[:10])
        )
    ordered = rows.sort_values("node_id").drop_duplicates("cluster_id")
    return {
        "owner_to_cluster": owner_to_cluster,
        "cluster_confidence": ordered.set_index("cluster_id")[
            "confidence_level"
        ].astype(str).to_dict(),
        "cluster_label": ordered.set_index("cluster_id")["full_name"]
        .astype(str)
        .to_dict(),
    }


def load_parcel_situs(path: Path) -> dict[str, str]:
    with path.open("rb") as handle:
        unified = pickle.load(handle)
    situs: dict[str, str] = {}
    for node, data in unified.nodes(data=True):
        if data.get("type") != "parcel":
            continue
        parcel_id = str(data.get("pid") or "").strip()
        if not parcel_id and str(node).startswith("parcel|"):
            parcel_id = str(node).split("|", 1)[1]
        if parcel_id:
            situs[parcel_id] = str(data.get("situs") or "")
    return situs


def _owner_cluster(party: str, owner_to_cluster: dict[str, str]) -> str | None:
    return owner_to_cluster.get(normalize_name(f"owner|{party}"))


def analyze_transactions(
    rows: list[dict],
    cluster_index: dict,
    *,
    amount_threshold: float = 50_000,
) -> tuple[list[dict], dict[str, int]]:
    """Return qualifying transaction/cluster-pair associations and coverage."""
    owner_to_cluster = cluster_index["owner_to_cluster"]
    confidence = cluster_index["cluster_confidence"]
    stats: Counter[str] = Counter()
    associations: list[dict] = []
    qualifying_parcels: set[str] = set()

    for transaction in iter_transfer_transactions(rows):
        stats["raw_rows"] += 1
        amount = transaction["amount"]
        if amount is None:
            stats["rows_with_invalid_amount"] += 1
            continue
        if amount <= amount_threshold:
            continue
        stats["amount_eligible_rows"] += 1
        parcel_id = transaction["parcel_id"]
        if not parcel_id:
            stats["rows_without_parcel_id"] += 1
            continue

        grantors: set[str] = set()
        grantees: set[str] = set()
        for party in transaction["grantors"]:
            cluster = _owner_cluster(party, owner_to_cluster)
            if cluster is None:
                stats["unresolved_grantor_parties"] += 1
            else:
                grantors.add(cluster)
        for party in transaction["grantees"]:
            cluster = _owner_cluster(party, owner_to_cluster)
            if cluster is None:
                stats["unresolved_grantee_parties"] += 1
            else:
                grantees.add(cluster)
        if not grantors or not grantees:
            stats["rows_without_two_resolved_sides"] += 1
            continue

        cross_pairs = {
            (grantor, grantee)
            for grantor in grantors
            for grantee in grantees
            if grantor != grantee
        }
        if not cross_pairs:
            stats["rows_with_only_same_cluster_pairs"] += 1
            continue
        stats["rows_with_cross_entity_pair"] += 1
        stats["cross_entity_transaction_cluster_pairs"] += len(cross_pairs)

        qualifying = {
            (grantor, grantee)
            for grantor, grantee in cross_pairs
            if confidence.get(grantor, "LOW") == "HIGH"
            and confidence.get(grantee, "LOW") == "HIGH"
        }
        if not qualifying:
            continue
        stats["rows_with_both_high_pair"] += 1
        stats["both_high_transaction_cluster_pairs"] += len(qualifying)
        qualifying_parcels.add(parcel_id)
        if len(qualifying) > 1:
            stats["both_high_rows_with_multiple_cluster_pairs"] += 1

        for grantor, grantee in sorted(qualifying):
            associations.append(
                {
                    "transaction_id": transaction["transaction_id"],
                    "source_row": transaction["source_row"],
                    "parcel_id": parcel_id,
                    "amount": amount,
                    "date": transaction["date"] or "",
                    "book_page": transaction["book_page"] or "",
                    "raw_grantor": transaction["raw_grantor"],
                    "raw_grantee": transaction["raw_grantee"],
                    "cluster_a": grantor,
                    "cluster_b": grantee,
                    "conf_a": confidence.get(grantor, "LOW"),
                    "conf_b": confidence.get(grantee, "LOW"),
                }
            )

    stats["both_high_parcels"] = len(qualifying_parcels)
    keys = [
        "raw_rows",
        "rows_with_invalid_amount",
        "amount_eligible_rows",
        "rows_without_parcel_id",
        "unresolved_grantor_parties",
        "unresolved_grantee_parties",
        "rows_without_two_resolved_sides",
        "rows_with_only_same_cluster_pairs",
        "rows_with_cross_entity_pair",
        "cross_entity_transaction_cluster_pairs",
        "rows_with_both_high_pair",
        "both_high_transaction_cluster_pairs",
        "both_high_rows_with_multiple_cluster_pairs",
        "both_high_parcels",
    ]
    return associations, {key: int(stats[key]) for key in keys}


def build_graph(
    associations: list[dict],
    cluster_index: dict,
    parcel_situs: dict[str, str],
) -> nx.MultiDiGraph:
    """Build transaction-keyed half-edges without overwriting provenance."""
    graph = nx.MultiDiGraph()
    labels = cluster_index["cluster_label"]
    confidence = cluster_index["cluster_confidence"]
    for item in associations:
        for cluster in (item["cluster_a"], item["cluster_b"]):
            node = f"cluster:{cluster}"
            if node not in graph:
                graph.add_node(
                    node,
                    type="cluster",
                    cluster_id=cluster,
                    label=labels.get(cluster, f"Cluster {cluster}"),
                    confidence=confidence.get(cluster, "LOW"),
                )
        parcel_node = f"parcel|{item['parcel_id']}"
        if parcel_node not in graph:
            address = parcel_situs.get(item["parcel_id"], "")
            graph.add_node(
                parcel_node,
                type="parcel",
                parcel_id=item["parcel_id"],
                situs=address,
                label=address[:50] if address else parcel_node,
            )

        common = {
            "transaction_id": item["transaction_id"],
            "source_row": item["source_row"],
            "parcel_id": item["parcel_id"],
            "cluster_a": item["cluster_a"],
            "cluster_b": item["cluster_b"],
            "conf_a": item["conf_a"],
            "conf_b": item["conf_b"],
            "amount": item["amount"],
            "total_amount": item["amount"],
            "date": item["date"],
            "reference": item["book_page"],
            "book_page": item["book_page"],
            "raw_grantor": item["raw_grantor"],
            "raw_grantee": item["raw_grantee"],
            "weight": 1,
            "n_transactions": 1,
        }
        key = (
            f"{item['transaction_id']}:{item['cluster_a']}:"
            f"{item['cluster_b']}"
        )
        graph.add_edge(
            f"cluster:{item['cluster_a']}",
            parcel_node,
            key=f"{key}:out",
            direction="out",
            **common,
        )
        graph.add_edge(
            parcel_node,
            f"cluster:{item['cluster_b']}",
            key=f"{key}:in",
            direction="in",
            **common,
        )
    return graph


def rank_parcels(
    associations: list[dict],
    parcel_situs: dict[str, str],
    *,
    top_n: int = 20,
) -> pd.DataFrame:
    """Rank parcels by source transactions, deduplicating joint-party pairs."""
    transactions: dict[str, dict[str, dict]] = defaultdict(dict)
    pairs: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for item in associations:
        parcel = item["parcel_id"]
        transactions[parcel].setdefault(item["transaction_id"], item)
        pairs[parcel].add((item["cluster_a"], item["cluster_b"]))

    rows = []
    for parcel, parcel_transactions in transactions.items():
        items = list(parcel_transactions.values())
        clusters = {
            cluster
            for pair in pairs[parcel]
            for cluster in pair
        }
        volume = sum(float(item["amount"] or 0.0) for item in items)
        dates = sorted(item["date"] for item in items if item["date"])
        rows.append(
            {
                "parcel_id": parcel,
                "situs": parcel_situs.get(parcel, ""),
                "observed_transfer_count": len(items),
                "distinct_clusters": len(clusters),
                "distinct_cluster_pairs": len(pairs[parcel]),
                "total_volume": volume,
                "avg_amount": volume / len(items),
                "first_transfer_date": dates[0] if dates else "",
                "last_transfer_date": dates[-1] if dates else "",
                "transaction_ids": ";".join(sorted(parcel_transactions)),
                "clusters": ";".join(sorted(clusters)),
            }
        )
    rows.sort(
        key=lambda row: (
            -row["observed_transfer_count"],
            -row["total_volume"],
            row["parcel_id"],
        )
    )
    return pd.DataFrame(rows[:top_n], columns=RANKING_COLUMNS)


def _component_layout(graph: nx.MultiDiGraph, seed: int) -> dict:
    """Lay out disconnected components separately on a deterministic grid."""
    components = sorted(
        nx.connected_components(graph.to_undirected()),
        key=lambda component: (-len(component), sorted(component)[0]),
    )
    columns = max(1, math.ceil(math.sqrt(len(components))))
    positions = {}
    for index, component in enumerate(components):
        subgraph = graph.subgraph(component)
        local = nx.spring_layout(
            subgraph,
            seed=seed + index,
            weight="weight",
            scale=1.0,
        )
        offset_x = (index % columns) * 3.2
        offset_y = -(index // columns) * 3.2
        for node, (x, y) in local.items():
            positions[node] = (x + offset_x, y + offset_y)
    return positions


def render_png(
    graph: nx.MultiDiGraph,
    output_path: Path,
    *,
    seed: int = 42,
    dpi: int = 300,
) -> None:
    """Render a force-directed network or an explicit no-data image."""
    if graph.number_of_nodes() == 0:
        fig, ax = plt.subplots(figsize=(16, 10), facecolor="#0f0f1a")
        ax.set_facecolor("#0f0f1a")
        ax.text(
            0.5,
            0.56,
            "No qualifying parcel transfers",
            ha="center",
            va="center",
            fontsize=26,
            color="#eaeaea",
            weight="bold",
            transform=ax.transAxes,
        )
        ax.text(
            0.5,
            0.43,
            "Amount > $50,000 | Different entities | Both endpoints HIGH\n"
            "Source: last-transfer snapshot (not deed history)",
            ha="center",
            va="center",
            fontsize=14,
            color="#b8b8c8",
            transform=ax.transAxes,
        )
        ax.axis("off")
        fig.savefig(output_path, dpi=dpi, facecolor=fig.get_facecolor())
        plt.close(fig)
        return

    positions = _component_layout(graph, seed)
    fig, ax = plt.subplots(figsize=(24, 24), facecolor="#0f0f1a")
    ax.set_facecolor("#0f0f1a")
    cluster_nodes = [
        node for node, data in graph.nodes(data=True) if data.get("type") == "cluster"
    ]
    parcel_nodes = [
        node for node, data in graph.nodes(data=True) if data.get("type") == "parcel"
    ]
    widths = [
        0.5 + min(float(data.get("amount") or 0) / 100_000, 3.0)
        for _, _, _, data in graph.edges(keys=True, data=True)
    ]
    colors = [
        "#00d4aa" if data.get("direction") == "out" else "#008866"
        for _, _, _, data in graph.edges(keys=True, data=True)
    ]
    nx.draw_networkx_edges(
        graph,
        positions,
        edge_color=colors,
        width=widths,
        alpha=0.3,
        arrows=True,
        arrowsize=10,
        ax=ax,
    )
    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=parcel_nodes,
        node_color="#ffaa00",
        node_size=80,
        node_shape="s",
        alpha=0.9,
        ax=ax,
    )
    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=cluster_nodes,
        node_color="#00d4aa",
        node_size=[100 + graph.degree(node) * 30 for node in cluster_nodes],
        alpha=0.95,
        ax=ax,
    )
    label_nodes = sorted(
        cluster_nodes + parcel_nodes,
        key=lambda node: (-graph.degree(node), node),
    )[:40]
    nx.draw_networkx_labels(
        graph,
        positions,
        labels={node: graph.nodes[node].get("label", node) for node in label_nodes},
        font_size=7,
        font_color="#eaeaea",
        ax=ax,
    )
    ax.set_title(
        "High-Value Parcel Transfer Network\n"
        "Cluster -> Parcel -> Cluster | Amount > $50K | Both endpoints HIGH\n"
        "Observed last-transfer snapshot; not historical deed-chain flips",
        fontsize=18,
        color="#eaeaea",
        pad=20,
    )
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default=str(DEFAULT_RAW))
    parser.add_argument("--clusters", default=str(DEFAULT_CLUSTERS))
    parser.add_argument("--unified", default=str(DEFAULT_UNIFIED))
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("--amount-threshold", type=float, default=50_000)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dpi", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.top_n < 1 or args.dpi < 1:
        parser.error("--top-n and --dpi must be positive")
    raw_path = Path(args.raw).expanduser()
    clusters_path = Path(args.clusters).expanduser()
    unified_path = Path(args.unified).expanduser()
    for path in (raw_path, clusters_path, unified_path):
        if not path.is_file():
            parser.error(f"input not found: {path}")
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading clusters: {clusters_path}")
    cluster_index = build_cluster_index(pd.read_parquet(clusters_path))
    print(f"Loading parcel situs: {unified_path}")
    parcel_situs = load_parcel_situs(unified_path)
    print(f"Loading raw transactions: {raw_path}")
    rows = load_rows(raw_path)
    associations, coverage = analyze_transactions(
        rows,
        cluster_index,
        amount_threshold=args.amount_threshold,
    )
    graph = build_graph(associations, cluster_index, parcel_situs)
    ranking = rank_parcels(associations, parcel_situs, top_n=args.top_n)

    graph_path = output_dir / "high_value_parcel_network_high_conf.graphml"
    png_path = output_dir / "high_value_parcel_transfer_network_high_conf.png"
    ranking_path = output_dir / "top20_parcel_transfers.csv"
    audit_path = output_dir / "parcel_transfer_audit.json"
    nx.write_graphml(graph, graph_path)
    ranking.to_csv(ranking_path, index=False)
    render_png(graph, png_path, seed=args.seed, dpi=args.dpi)

    audit = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_grain": "last_transfer_snapshot",
        "historical_flip_ranking_supported": False,
        "filters": {
            "amount_rule": f"row amount > {args.amount_threshold}",
            "different_endpoint_clusters": True,
            "both_endpoint_confidence": "HIGH",
        },
        "inputs": {
            "raw": str(raw_path),
            "clusters": str(clusters_path),
            "unified": str(unified_path),
        },
        "coverage": coverage,
        "qualifying_association_rows": len(associations),
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "ranking_rows": len(ranking),
        "outputs": {
            "graphml": str(graph_path),
            "png": str(png_path),
            "ranking": str(ranking_path),
        },
    }
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(coverage, indent=2))
    print(f"GraphML: {graph_path}")
    print(f"PNG: {png_path}")
    print(f"Ranking: {ranking_path}")
    print(f"Audit: {audit_path}")
    if not associations:
        print("No transactions satisfied all requested filters; empty outputs written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
