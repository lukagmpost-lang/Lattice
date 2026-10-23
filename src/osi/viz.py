"""Interactive HTML graph visualization with community-aware styling."""
from __future__ import annotations

import math
from pathlib import Path
import json

import networkx as nx

try:
    from pyvis.network import Network
except ImportError:
    Network = None

PALETTE = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
]

NEGATIVE_LABELS = {"tense", "hostile", "condescending", "dismissive", "passive_aggressive"}
POSITIVE_LABELS = {"warm", "friendly"}

def _polarity_color(pos, neg, total, llm_polarity=None, llm_label=None):
    if llm_label:
        lbl = str(llm_label).strip().lower()
        if lbl in POSITIVE_LABELS:
            return "#3fa34d"
        if lbl in NEGATIVE_LABELS:
            return "#c43d3d"
        if lbl == "neutral":
            return "rgba(255,255,255,0.15)"
    if llm_polarity is not None:
        p = float(llm_polarity)
    elif total == 0 or (pos + neg) == 0:
        return "rgba(255,255,255,0.15)"
    else:
        p = (pos - neg) / max(pos + neg, 1)
    if p > 0.3:
        return "#3fa34d"
    if p < -0.3:
        return "#c43d3d"
    return "rgba(255,255,255,0.15)"

def _is_llm_scored(data):
    return data.get("llm_polarity") is not None

def audit_communities(graph, min_size=3):
    communities = list(nx.community.louvain_communities(graph, seed=42))
    pr = nx.pagerank(graph, weight="weight")
    results = []
    for i, members in enumerate(communities):
        if len(members) < min_size:
            continue
        ms = set(members)
        n = len(members)
        max_internal = n * (n - 1) / 2
        internal = [(u, v) for u, v in graph.edges() if u in ms and v in ms]
        density = len(internal) / max_internal if max_internal else 0.0
        hub = max(members, key=lambda m: pr.get(m, 0))
        hub_edges = sum(1 for u, v in internal if hub in (u, v))
        hub_share = hub_edges / len(internal) if internal else 0.0
        if density > 0.3 and hub_share < 0.6:
            verdict = "real"
        elif hub_share > 0.75 and density < 0.15:
            verdict = "artifact"
        else:
            verdict = "mixed"
        results.append({"id": i, "members": members, "size": n, "hub": hub,
                        "density": density, "hub_share": hub_share,
                        "verdict": verdict})
    return results

def _community_layout(graph, communities, node_comm, seed=42):
    comm_graph = nx.Graph()
    for i in range(len(communities)):
        comm_graph.add_node(i)
    for u, v in graph.edges():
        cu, cv = node_comm.get(u), node_comm.get(v)
        if cu is None or cv is None or cu == cv:
            continue
        if comm_graph.has_edge(cu, cv):
            comm_graph[cu][cv]["weight"] += 1
        else:
            comm_graph.add_edge(cu, cv, weight=1)
            
    if len(comm_graph) > 1:
        comm_pos = nx.spring_layout(comm_graph, scale=4.0, seed=seed,
                                    weight="weight", k=3.0, iterations=200)
    else:
        comm_pos = {0: (0.0, 0.0)}
        
    pos = {}
    for comm_id, members in enumerate(communities):
        cx, cy = comm_pos.get(comm_id, (0.0, 0.0))
        n = len(members)
        if n == 1:
            pos[list(members)[0]] = (cx, cy)
            continue
        radius = 0.6 + 0.08 * math.sqrt(n)
        for i, node in enumerate(members):
            angle = 2 * math.pi * i / n
            jitter_x = 0.05 * math.cos(i * 7.3)
            jitter_y = 0.05 * math.sin(i * 5.1)
            pos[node] = (cx + radius * math.cos(angle) + jitter_x,
                         cy + radius * math.sin(angle) + jitter_y)
    return pos

def _galaxy_layout(graph, scale=4.0, seed=42):
    """Gephi-style layout with a Virtual Gravity Center to pull isolated nodes inward."""
    G_grav = graph.to_undirected().copy()
    center = '__GRAVITY_CENTER__'
    G_grav.add_node(center)
    
    # Connect all nodes to the gravity center to pull them in
    for n in G_grav.nodes():
        if n != center:
            G_grav.add_edge(n, center, weight=0.1)
            
    try:
        # Kamada-Kawai forces a compact, non-ring shape
        pos = nx.kamada_kawai_layout(G_grav)
    except Exception:
        pos = nx.spring_layout(G_grav, weight='weight', scale=scale, iterations=100, seed=seed)
        
    if center in pos:
        del pos[center]
    return pos

def _filter_edges(graph, top_n=120, min_weight=1.0):
    edges = [e for e in graph.edges(data=True) if e[2].get("weight", 1) >= min_weight]
    if top_n is not None and len(edges) > top_n:
        edges = sorted(edges, key=lambda e: -e[2].get("weight", 0))[:top_n]
    kept = nx.Graph()
    kept.add_nodes_from(graph.nodes(data=True))
    for u, v, d in edges:
        kept.add_edge(u, v, **d)
    return kept

def render_interactive_html(graph, out_path, top_edges=10000, min_edge_weight=1.0, top_labels=100, **kwargs):
    import networkx as nx
    from pyvis.network import Network

    # 1. Keep only largest connected component
    G = nx.Graph()
    for node, data in graph.nodes(data=True):
        G.add_node(node, **data)
    for u, v, data in graph.edges(data=True):
        if data.get("weight", 1) >= min_edge_weight:
            G.add_edge(u, v, **data)

    if G.number_of_nodes() > 0:
        components = sorted(nx.connected_components(G), key=len, reverse=True)
        G = G.subgraph(components[0]).copy()

    # 2. Kamada-Kawai Layout (Mathematical clusters, no physics engine)
    print("Computing Kamada-Kawai layout...")
    pos = nx.kamada_kawai_layout(G)

    # 3. Build Pyvis (White background, faint gray edges)
    net = Network(height="100vh", width="100%", bgcolor="#ffffff", font_color="#000000", directed=False, cdn_resources="in_line")

    communities = list(nx.community.louvain_communities(G, seed=42))
    node_comm = {node: i for i, c in enumerate(communities) for node in c}
    PALETTE = ["#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F", "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC"]
    pr = nx.pagerank(G, weight='weight')
    top_100 = set(sorted(pr, key=pr.get, reverse=True)[:100])

    for node, data in G.nodes(data=True):
        msg_count = data.get("message_count", 1)
        size = min(10 + (msg_count * 1.5), 30)
        color = PALETTE[node_comm.get(node, 0) % len(PALETTE)]
        label = str(node) if node in top_100 else " "
        
        x, y = pos.get(node, (0, 0))
        net.add_node(str(node), label=label, size=size, color=color, x=float(x)*1000, y=float(y)*1000, physics=False, title=f"{node} ({msg_count} msgs)")

    for u, v, data in G.edges(data=True):
        net.add_edge(str(u), str(v), value=data.get("weight", 1), color="rgba(0,0,0,0.15)")

    net.set_options("""
    var options = {
      "physics": {"enabled": false},
      "nodes": {"borderWidth": 0.5, "font": {"size": 12, "color": "#000000", "strokeWidth": 0}},
      "edges": {"smooth": false}
    }
    """)
    net.save_graph(str(out_path))
    print("✅ Kamada-Kawai layout rendered successfully.")

    with open(out_path) as f: html = f.read()
    btns = """
    <div style="position:fixed; top:15px; right:15px; z-index:9999; display:flex; gap:10px;">
        <button onclick="window.open('/api/export/gexf/' + window.location.pathname.split('/').pop(), '_blank')" style="font-family:monospace; font-size:12px; padding:8px 14px; background:#161616; color:#fff; border:1px solid #444; border-radius:4px; cursor:pointer;">Export GEXF</button>
        <button onclick="window.open('/api/export/md/' + window.location.pathname.split('/').pop(), '_blank')" style="font-family:monospace; font-size:12px; padding:8px 14px; background:#161616; color:#fff; border:1px solid #444; border-radius:4px; cursor:pointer;">Export Findings</button>
        <button onclick="window.open('/api/graph/png/' + window.location.pathname.split('/').pop(), '_blank')" style="font-family:monospace; font-size:12px; padding:8px 14px; background:#161616; color:#fff; border:1px solid #444; border-radius:4px; cursor:pointer;">Save PNG</button>
    </div>
    """
    html = html.replace('</body>', btns + '</body>')
    with open(out_path, 'w') as f: f.write(html)
    return out_path



def _inject_extras(out, comm_list, pr, audits, vis, full, node_comm, top_set):
    html = out.read_text(encoding="utf-8")

    rows = []
    for i, c in enumerate(comm_list[:12]):
        color = PALETTE[i % len(PALETTE)]
        a = audits.get(i, {})
        best = a.get("hub", max(c, key=lambda n: pr.get(n, 0))) if c else "?"
        verdict = a.get("verdict", "?")
        rows.append(
            f'<div class="osi-row"><span class="osi-dot" style="background:{color}">'
            f'</span>{len(c)} &middot; <b>{best}</b> <span style="color:#888">'
            f'[{verdict}]</span></div>'
        )
    
    more_text = f'<div style="color:#666;margin-top:5px;">...and {len(comm_list)-12} more</div>' if len(comm_list) > 12 else ""

    legend = (
        '<div id="osi-legend" style="position:absolute;top:14px;left:14px;'
        'background:rgba(15,15,15,0.94);border:1px solid #333;border-radius:8px;'
        'padding:14px 16px;font-family:arial;font-size:13px;color:#eee;'
        'max-height:80vh;overflow:auto;z-index:9999">'
        '<div style="font-weight:bold;margin-bottom:8px;font-size:14px">Communities</div>'
        + "".join(rows) + more_text +
        '<div style="margin-top:14px;font-weight:bold;font-size:14px">Edge color</div>'
        '<div class="osi-row"><span class="osi-dot" style="background:#3fa34d">'
        '</span>positive</div>'
        '<div class="osi-row"><span class="osi-dot" style="background:rgba(255,255,255,0.15)">'
        '</span>neutral</div>'
        '<div class="osi-row"><span class="osi-dot" style="background:#c43d3d">'
        '</span>negative</div>'
        '<div style="margin-top:14px;font-weight:bold;font-size:14px">Shown</div>'
        f'<div class="osi-row">{vis.number_of_edges()} edges '
        f'(of {full.number_of_edges()})</div>'
        '</div>'
        '<style>'
        '.osi-row{display:flex;align-items:center;gap:8px;margin:3px 0}'
        '.osi-dot{width:14px;height:14px;border-radius:50%;display:inline-block;'
        'border:1px solid #555}'
        '</style>'
    )

    png_button = """
    <div style="position:absolute; top:14px; right:14px; z-index:9999;">
        <button id="download-png-btn" onclick="window.open('/api/graph/png/' + window.location.pathname.split('/').pop(), '_blank')" style="font-family:inherit; font-size:12px; padding:8px 14px; background:#161616; color:#fff; border:1px solid #444; border-radius:4px; cursor:pointer;">
            Save Full PNG
        </button>
    </div>
    """

    html = html.replace("<body>", "<body>" + legend + png_button)
    out.write_text(html, encoding="utf-8")
