"""Render the entity-resolved Cuyahoga graph with the archived viz.py style."""
from __future__ import annotations

import argparse
import html
import json
import math
import random
from collections import Counter
from pathlib import Path

import networkx as nx
import pandas as pd
from pyvis.network import Network

PALETTE = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]
RELATION_STYLES = {
    "married_to": {"label": "Marriage", "color": "#ff1493", "width": 1.8},
    "divorced_from": {"label": "Divorce", "color": "#9c27b0", "width": 1.8},
    "litigated_with": {"label": "Litigation", "color": "#008b9a", "width": 1.2},
    "mentioned_in_case": {
        "label": "Docket mention (not necessarily a litigant)",
        "color": "#b8b8b8", "width": 0.8, "dashes": [6, 4],
    },
}


def resolved_neighborhood(graph: nx.Graph) -> nx.Graph:
    """Keep resolved transfer context and every verified social relationship."""
    resolved = {
        node for node, data in graph.nodes(data=True)
        if data.get("resolved") is True or str(node).startswith("cluster:")
    }
    if not resolved:
        raise ValueError("graph contains no entity-resolved cluster nodes")
    keep = set(resolved)
    for source, target, data in graph.edges(data=True):
        if data.get("relation") in RELATION_STYLES:
            keep.add(source)
            keep.add(target)
    for node in resolved:
        if graph.is_directed():
            keep.update(graph.predecessors(node))
            keep.update(graph.successors(node))
        else:
            keep.update(graph.neighbors(node))
    return graph.subgraph(keep).copy()


def cluster_members(path: Path) -> dict[str, list[dict[str, str]]]:
    clusters = pd.read_parquet(
        path, columns=["cluster_id", "node_id", "full_name", "confidence_level"]
    )
    members: dict[str, list[dict[str, str]]] = {}
    for cluster_id, rows in clusters.groupby("cluster_id", sort=True):
        members[str(cluster_id)] = [
            {
                "node_id": str(row.node_id),
                "full_name": str(row.full_name),
                "confidence_level": str(row.confidence_level),
            }
            for row in rows.itertuples(index=False)
        ]
    return members


def spring_layout(subgraph: nx.Graph, *, seed: int) -> dict[str, tuple[float, float]]:
    """Use compiled igraph for large components, with a NetworkX fallback."""
    if len(subgraph) > 500:
        try:
            import igraph
        except ImportError:
            pass
        else:
            print(
                f"Using compiled igraph layout for {len(subgraph):,}-node component...",
                flush=True,
            )
            nodes = sorted(subgraph)
            indices = {node: index for index, node in enumerate(nodes)}
            edges = [(indices[source], indices[target]) for source, target in subgraph.edges()]
            weights = [float(data.get("weight", 1.0)) for _, _, data in subgraph.edges(data=True)]
            compiled = igraph.Graph(n=len(nodes), edges=edges, directed=False)
            rng = random.Random(seed)
            initial = [[rng.uniform(-1, 1), rng.uniform(-1, 1)] for _ in nodes]
            layout = compiled.layout_fruchterman_reingold(
                weights=weights, niter=60, seed=initial, grid="auto"
            )
            coordinates = layout.coords
            xs = [point[0] for point in coordinates]
            ys = [point[1] for point in coordinates]
            center_x = (max(xs) + min(xs)) / 2.0
            center_y = (max(ys) + min(ys)) / 2.0
            scale = max((max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0, 1e-12)
            return {
                node: ((coordinates[index][0] - center_x) / scale,
                       (coordinates[index][1] - center_y) / scale)
                for index, node in enumerate(nodes)
            }
    return nx.spring_layout(
        subgraph, seed=seed, iterations=60, weight="weight", scale=1.0
    )


def packed_layout(
    graph: nx.Graph, *, seed: int = 42, spacing: float = 1.25
) -> dict[str, tuple[float, float]]:
    """Lay out components independently and pack them without overlap."""
    if spacing <= 0:
        raise ValueError("spacing must be greater than zero")
    undirected = graph.to_undirected()
    components = sorted(nx.connected_components(undirected), key=len, reverse=True)
    positions: dict[str, tuple[float, float]] = {}
    x_cursor = y_cursor = row_height = 0.0
    row_width = 100.0
    for component in components:
        subgraph = undirected.subgraph(component)
        if len(component) == 1:
            local = {next(iter(component)): (0.0, 0.0)}
        elif len(component) <= 40:
            local = nx.kamada_kawai_layout(subgraph)
        else:
            local = spring_layout(subgraph, seed=seed)
        radius = max(1.5, math.sqrt(len(component)) / 6.0) * spacing
        width = 2.0 * radius + 1.0
        if x_cursor and x_cursor + width > row_width:
            x_cursor = 0.0
            y_cursor -= row_height + 1.0
            row_height = 0.0
        center_x, center_y = x_cursor + radius, y_cursor - radius
        for node, (x, y) in local.items():
            positions[node] = (center_x + float(x) * radius, center_y - float(y) * radius)
        x_cursor += width
        row_height = max(row_height, 2.0 * radius)
    return positions


def _node_title(node: str, data: dict, members: dict[str, list[dict[str, str]]]) -> str:
    if not str(node).startswith("cluster:"):
        kind = "organization" if str(node).startswith("org|") else "owner"
        return f"<b>{html.escape(str(data.get('label', node)))}</b><br>Unresolved {kind}"
    cluster_id = str(node).removeprefix("cluster:")
    rows = members.get(cluster_id, [])
    lines = [
        f"<b>{html.escape(str(data.get('label', node)))}</b>",
        f"Cluster ID: {html.escape(cluster_id)}",
        f"Confidence: {html.escape(str(data.get('confidence_level', 'UNKNOWN')))}",
        f"Merged records: {len(rows) or int(data.get('cluster_size', 0))}",
        "<hr><b>Entity-resolution members</b>",
    ]
    lines.extend(
        f"{html.escape(row['full_name'])}<br><small>{html.escape(row['node_id'])}</small>"
        for row in rows
    )
    return "<br>".join(lines)


def render_resolved_graph(
    graph_path: Path,
    clusters_path: Path,
    output_path: Path,
    *,
    seed: int = 42,
    spacing: float = 1.25,
) -> dict[str, int]:
    graph = nx.read_graphml(graph_path)
    graph = resolved_neighborhood(graph)
    print(
        f"Rendering {graph.number_of_nodes():,} nodes and {graph.number_of_edges():,} edges",
        flush=True,
    )
    members = cluster_members(clusters_path)
    print("Computing deterministic component layouts...", flush=True)
    positions = packed_layout(graph, seed=seed, spacing=spacing)
    print("Computing communities and labels...", flush=True)
    undirected = graph.to_undirected()
    communities = nx.community.louvain_communities(undirected, seed=seed, weight="weight")
    node_community = {
        node: index for index, community in enumerate(communities) for node in community
    }
    pagerank = nx.pagerank(undirected, weight="weight")
    labelled = set(sorted(pagerank, key=pagerank.get, reverse=True)[:100])
    resolved_count = sum(str(node).startswith("cluster:") for node in graph)
    relation_counts = Counter(
        str(data.get("relation", "transfer")) for _, _, data in graph.edges(data=True)
    )

    net = Network(
        height="100vh", width="100%", bgcolor="#ffffff", font_color="#000000",
        directed=True, cdn_resources="in_line",
    )
    for node, data in graph.nodes(data=True):
        is_resolved = str(node).startswith("cluster:")
        confidence = str(data.get("confidence_level", ""))
        label = str(data.get("label", node)) if is_resolved and (
            node in labelled or confidence == "HIGH"
        ) else " "
        x, y = positions[node]
        net.add_node(
            str(node),
            label=label,
            size=min(12 + 2 * int(data.get("cluster_size", 0)), 30) if is_resolved else 4,
            color={
                "background": PALETTE[node_community[node] % len(PALETTE)] if is_resolved else "#c7c7c7",
                "border": "#9c6500" if confidence == "HIGH" else "#ffffff",
            },
            borderWidth=3 if confidence == "HIGH" else 1,
            x=x * 180,
            y=y * 180,
            physics=False,
            title=_node_title(node, data, members),
        )
    for source, target, data in graph.edges(data=True):
        relation = str(data.get("relation", "transfer"))
        if relation == "transfer":
            transactions = int(float(data.get("n_transactions", data.get("weight", 1))))
            amount = float(data.get("total_amount", 0.0))
            title = (
                f"<b>Property transfer</b><br>{html.escape(source)} &rarr; {html.escape(target)}<br>"
                f"Transactions: {transactions:,}<br>Observed amount: ${amount:,.2f}"
            )
            net.add_edge(
                str(source), str(target),
                value=max(1.0, math.log1p(transactions)),
                color="rgba(0,0,0,0.15)",
                arrows={"to": {"enabled": True, "scaleFactor": 0.45}},
                title=title,
            )
            continue
        style = RELATION_STYLES[relation]
        title_parts = [
            f"<b>{html.escape(style['label'])}</b>",
            f"{html.escape(source)} &mdash; {html.escape(target)}",
        ]
        if data.get("case_no"):
            title_parts.append(f"Case: {html.escape(str(data['case_no']))}")
        if data.get("caption"):
            title_parts.append(f"Caption: {html.escape(str(data['caption']))}")
        if data.get("reliability"):
            title_parts.append(f"Reliability: {html.escape(str(data['reliability']))}")
        if data.get("match_method"):
            title_parts.append(f"Match method: {html.escape(str(data['match_method']))}")
        title_parts.append(
            f"Original source pairs: {int(data.get('n_source_edges', 1)):,}"
        )
        options = {
            "color": style["color"],
            "width": style["width"],
            "arrows": {"to": {"enabled": False}},
            "title": "<br>".join(title_parts),
        }
        if "dashes" in style:
            options["dashes"] = style["dashes"]
        net.add_edge(str(source), str(target), **options)
    net.set_options(json.dumps({
        "physics": {"enabled": False},
        "nodes": {"font": {"size": 12, "color": "#000000", "strokeWidth": 0}},
        "edges": {"smooth": False},
        "interaction": {"hover": True, "navigationButtons": True, "tooltipDelay": 100},
    }))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print("Writing standalone HTML...", flush=True)
    net.save_graph(str(output_path))
    unresolved_count = graph.number_of_nodes() - resolved_count
    has_social = any(relation in relation_counts for relation in RELATION_STYLES)
    if has_social:
        relation_summary = " &middot; ".join([
            f"Transfers {relation_counts.get('transfer', 0):,}",
            f"<span style='color:#ff1493'>Marriages {relation_counts.get('married_to', 0):,}</span>",
            f"<span style='color:#9c27b0'>Divorces {relation_counts.get('divorced_from', 0):,}</span>",
            f"<span style='color:#008b9a'>Litigation {relation_counts.get('litigated_with', 0):,}</span>",
            f"Docket mentions {relation_counts.get('mentioned_in_case', 0):,} (dashed)",
        ])
        heading = "Entity-resolved multi-layer relationship graph"
    else:
        relation_summary = f"Directed property-transfer edges {relation_counts.get('transfer', 0):,}"
        heading = "Entity-resolved merged transfer graph"
    banner = f"""
    <div style="position:fixed;top:12px;left:12px;z-index:9999;background:rgba(255,255,255,.95);
      border:1px solid #ccc;border-radius:6px;padding:10px 14px;font:13px Arial;color:#222;max-width:760px">
      <b>{heading}</b><br>
      {resolved_count:,} cluster nodes &middot; {unresolved_count:,} unresolved context nodes &middot;
      {graph.number_of_edges():,} edges<br>{relation_summary}<br>
      Large colored nodes = resolved entities; gray = unresolved; gold border = HIGH.
      Social edges are undirected; transfers have arrows.<br>
      Hover clusters for merged records and edges for evidence. Node colors show Louvain communities.
    </div>"""
    output_path.write_text(
        output_path.read_text(encoding="utf-8").replace("<body>", "<body>" + banner),
        encoding="utf-8",
    )
    return {
        "resolved_nodes": resolved_count,
        "unresolved_context_nodes": unresolved_count,
        "edges": graph.number_of_edges(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=Path("cuyahoga_pruned_graph.graphml"))
    parser.add_argument("--clusters", type=Path, default=Path("cuyahoga_resolved_clusters.parquet"))
    parser.add_argument("--output", type=Path, default=Path("cuyahoga_resolved_graph.html"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--spacing", type=float, default=1.25,
        help="layout spacing multiplier; values above 1 reduce node clustering (default: 1.25)",
    )
    args = parser.parse_args()
    stats = render_resolved_graph(
        args.graph, args.clusters, args.output, seed=args.seed, spacing=args.spacing
    )
    print(json.dumps(stats, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
