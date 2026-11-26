"""Merge verified social edges into the entity-resolved Cuyahoga transfer graph."""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd

from splink_graph_pipeline import write_graphml

SOCIAL_RELATIONS = (
    "married_to",
    "divorced_from",
    "litigated_with",
    "mentioned_in_case",
)
SOCIAL_RELATION_SET = frozenset(SOCIAL_RELATIONS)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def cluster_definitions(clusters: pd.DataFrame) -> tuple[dict[str, str], dict[str, dict]]:
    """Return owner-to-cluster mappings and deterministic display metadata."""
    required = {"node_id", "cluster_id", "full_name", "confidence_level"}
    missing = required.difference(clusters.columns)
    if missing:
        raise ValueError(f"cluster input is missing columns: {sorted(missing)}")
    node_to_cluster = dict(
        zip(clusters["node_id"].astype(str), clusters["cluster_id"].astype(str))
    )
    sizes = clusters.groupby(clusters["cluster_id"].astype(str)).size()
    preferred = clusters.sort_values("node_id").drop_duplicates("cluster_id")
    definitions = {
        str(row.cluster_id): {
            "label": str(row.full_name),
            "resolved": True,
            "cluster_size": int(sizes.loc[str(row.cluster_id)]),
            "confidence_level": str(row.confidence_level),
            "kind": "person_cluster",
        }
        for row in preferred.itertuples(index=False)
    }
    return node_to_cluster, definitions


def build_multilayer_graph(
    transfer_graph: nx.DiGraph,
    unified_graph: nx.Graph,
    clusters: pd.DataFrame,
) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    """Overlay verified social evidence without discarding parallel transfer edges.

    NetworkX has no mixed directed/undirected multigraph. The container is a
    MultiDiGraph so transfer direction remains native; each social edge has
    ``directed=False`` and its endpoint ordering carries no semantic direction.
    """
    node_to_cluster, definitions = cluster_definitions(clusters)
    output = nx.MultiDiGraph()
    output.add_nodes_from(transfer_graph.nodes(data=True))
    for source, target, data in transfer_graph.edges(data=True):
        attrs = dict(data)
        attrs["relation"] = "transfer"
        attrs["directed"] = True
        attrs["layer"] = "property_transfer"
        output.add_edge(source, target, **attrs)

    input_counts: Counter[str] = Counter()
    duplicate_counts: Counter[str] = Counter()
    self_loop_counts: Counter[str] = Counter()
    unresolved_pair_counts: Counter[str] = Counter()
    social_clusters: set[str] = set()
    self_loops: list[dict[str, Any]] = []
    evidence_groups: dict[tuple, dict[str, Any]] = {}

    def mapped_node(node: str) -> str:
        cluster_id = node_to_cluster.get(str(node))
        return f"cluster:{cluster_id}" if cluster_id is not None else str(node)

    def ensure_node(original: str, mapped: str) -> None:
        if mapped in output:
            return
        if mapped.startswith("cluster:"):
            cluster_id = mapped.removeprefix("cluster:")
            output.add_node(mapped, **definitions[cluster_id])
            return
        source_data = unified_graph.nodes.get(original, {})
        prefix = str(original).partition("|")[0]
        output.add_node(
            mapped,
            label=str(source_data.get("name") or original),
            resolved=False,
            cluster_size=0,
            confidence_level="",
            kind=str(source_data.get("kind") or prefix or "unknown"),
        )

    for original_source, original_target, data in unified_graph.edges(data=True):
        relation = _text(data.get("relation"))
        if relation not in SOCIAL_RELATION_SET:
            continue
        input_counts[relation] += 1
        source = mapped_node(str(original_source))
        target = mapped_node(str(original_target))
        case_no = _text(data.get("case_no"))
        caption = _text(data.get("caption"))
        source_pair = tuple(sorted((str(original_source), str(original_target))))
        if source == target:
            self_loop_counts[relation] += 1
            self_loops.append({
                "relation": relation,
                "mapped_node": source,
                "source_pair": list(source_pair),
                "case_no": case_no,
                "caption": caption,
                "reason": "both endpoints collapsed to one entity; excluded as a self-relationship",
            })
            continue

        endpoints = tuple(sorted((source, target)))
        for endpoint in endpoints:
            if endpoint.startswith("cluster:"):
                social_clusters.add(endpoint)
        if not any(endpoint.startswith("cluster:") for endpoint in endpoints):
            unresolved_pair_counts[relation] += 1
        evidence_key = (
            relation,
            *endpoints,
            _text(data.get("source")),
            case_no,
            caption,
            _text(data.get("reliability")),
            _text(data.get("match_method")),
        )
        group = evidence_groups.get(evidence_key)
        if group is None:
            group = {"source_pairs": set()}
            evidence_groups[evidence_key] = group
        else:
            duplicate_counts[relation] += 1
        group["source_pairs"].add(source_pair)

    for evidence_key in sorted(evidence_groups):
        (
            relation,
            source,
            target,
            source_name,
            case_no,
            caption,
            reliability,
            match_method,
        ) = evidence_key
        ensure_node(source, source)
        ensure_node(target, target)
        group = evidence_groups[evidence_key]
        source_pairs = sorted(group["source_pairs"])
        encoded_key = json.dumps(evidence_key, separators=(",", ":"))
        evidence_id = hashlib.blake2b(
            encoded_key.encode("utf-8"), digest_size=12
        ).hexdigest()
        output.add_edge(
            source,
            target,
            key=f"social:{evidence_id}",
            relation=relation,
            layer="social",
            directed=False,
            source=source_name,
            case_no=case_no,
            caption=caption,
            reliability=reliability,
            match_method=match_method,
            weight=1.0,
            n_source_edges=len(source_pairs),
            source_pairs=[
                {"source": pair[0], "target": pair[1]} for pair in source_pairs
            ],
            evidence_id=evidence_id,
        )

    social_output_counts = Counter(
        data["relation"]
        for _, _, data in output.edges(data=True)
        if data.get("layer") == "social"
    )
    total_input = sum(input_counts.values())
    total_self_loops = sum(self_loop_counts.values())
    total_duplicates = sum(duplicate_counts.values())
    total_social_output = sum(social_output_counts.values())
    assert total_social_output + total_duplicates + total_self_loops == total_input
    represented_source_edges = sum(
        int(data["n_source_edges"])
        for _, _, data in output.edges(data=True)
        if data.get("layer") == "social"
    )
    assert represented_source_edges == total_input - total_self_loops

    audit = {
        "inputs": {
            "transfer_nodes": transfer_graph.number_of_nodes(),
            "transfer_edges": transfer_graph.number_of_edges(),
            "unified_nodes": unified_graph.number_of_nodes(),
            "unified_edges": unified_graph.number_of_edges(),
            "resolved_owner_records": len(node_to_cluster),
        },
        "social_input_edges": dict(sorted(input_counts.items())),
        "social_input_total": total_input,
        "social_output_edges": dict(sorted(social_output_counts.items())),
        "social_output_total": total_social_output,
        "deduplicated_mapped_edges": dict(sorted(duplicate_counts.items())),
        "deduplicated_mapped_total": total_duplicates,
        "collapsed_self_loops": dict(sorted(self_loop_counts.items())),
        "collapsed_self_loop_total": total_self_loops,
        "collapsed_self_loop_records": self_loops,
        "unresolved_unresolved_social_edges": dict(sorted(unresolved_pair_counts.items())),
        "represented_source_social_edges": represented_source_edges,
        "resolved_social_clusters": len(social_clusters),
        "direction_semantics": (
            "transfer edges are directed grantor-to-grantee; social edges are "
            "stored once with directed=false and unordered endpoint semantics"
        ),
        "outputs": {
            "nodes": output.number_of_nodes(),
            "edges": output.number_of_edges(),
            "transfer_edges": sum(
                data.get("relation") == "transfer"
                for _, _, data in output.edges(data=True)
            ),
            "social_edges": total_social_output,
        },
    }
    return output, audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transfer-graph", type=Path, default=Path("cuyahoga_pruned_graph.graphml"))
    parser.add_argument("--clusters", type=Path, default=Path("cuyahoga_resolved_clusters.parquet"))
    parser.add_argument(
        "--unified", type=Path, default=Path.home() / "Desktop" / "cuyahoga_unified.pkl"
    )
    parser.add_argument("--output", type=Path, default=Path("cuyahoga_multilayer_graph.graphml"))
    parser.add_argument("--audit", type=Path, default=Path("cuyahoga_multilayer_audit.json"))
    args = parser.parse_args()

    transfer_graph = nx.read_graphml(args.transfer_graph)
    with args.unified.expanduser().open("rb") as handle:
        unified_graph = pickle.load(handle)
    clusters = pd.read_parquet(args.clusters)
    graph, audit = build_multilayer_graph(transfer_graph, unified_graph, clusters)
    graphml_counts = write_graphml(graph, args.output)
    audit["outputs"].update(graphml_counts)
    args.audit.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))
    print(f"Wrote {args.output}")
    print(f"Wrote {args.audit}")


if __name__ == "__main__":
    main()
