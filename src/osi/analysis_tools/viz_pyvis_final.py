import pickle, os, networkx as nx
from networkx.algorithms import community
from pyvis.network import Network

print("Loading graph...")
G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

H = nx.Graph()
for u, v, d in G.edges(data=True):
    if u.startswith("owner|") and v.startswith("owner|"):
        H.add_edge(u, v, **d)

# 1. REMOVE SELF-LOOPS (Fixes the k_core crash)
self_loops = list(nx.selfloop_edges(H))
H.remove_edges_from(self_loops)
print(f"Removed {len(self_loops)} self-loops.")

# 2. K-Core Pruning (Removes isolated nodes and leaves)
print("Pruning graph to 2-core...")
core = nx.k_core(H, k=2)
print(f"Nodes after pruning: {core.number_of_nodes()}")

# 3. Keep only the top 4,000 most connected nodes (Browser limit)
top_nodes = sorted(core.degree, key=lambda x: x[1], reverse=True)[:4000]
H_sub = core.subgraph([n for n, d in top_nodes]).copy()
print(f"Visualizing top {H_sub.number_of_nodes()} nodes, {H_sub.number_of_edges()} edges")

# 4. Communities
print("Detecting communities...")
communities = list(community.louvain_communities(H_sub, seed=42))
node_comm = {n: i for i, c in enumerate(communities) for n in c}
neon_colors = ["#ff5733", "#33ff57", "#3357ff", "#f333ff", "#33fff6", "#f6ff33", "#ff3369", "#8e44ad", "#e67e22", "#1abc9c"]
node_colors = {n: neon_colors[node_comm[n] % len(neon_colors)] for n in H_sub.nodes()}

print("Building Vizpy HTML...")
net = Network(height="100vh", width="100%", bgcolor="#0a0a0a", font_color="#ffffff", directed=False, cdn_resources="in_line")

# Add Nodes
for n in H_sub.nodes():
    deg = H_sub.degree(n)
    # Size nodes by their degree (number of connections)
    size = 15 + (deg * 2)
    label = n.replace("owner|", "")
    
    # Add a white border so nodes pop against the dark background
    net.add_node(n, label=label, size=size, color={"background": node_colors[n], "border": "#ffffff"}, 
                 font={"size": 12, "strokeWidth": 2, "strokeColor": "#000000"})

# Add Edges with Context Colors
for u, v, d in H_sub.edges(data=True):
    rel = d.get("relation", "")
    if rel == "married_to":
        color = "#ff1493" # Pink
        width = 2
    elif rel == "divorced_from":
        color = "#ff8c00" # Orange
        width = 2
    elif rel == "litigated_with":
        color = "#00ffff" # Cyan
        width = 2
    else:
        color = "rgba(255, 255, 255, 0.2)" # Faint white for mentions
        width = 1
        
    net.add_edge(u, v, color=color, width=width, title=rel)

# 5. Configure Physics for a beautiful, stable layout
net.set_options("""
var options = {
  "nodes": {
    "borderWidth": 1,
    "borderWidthSelected": 2
  },
  "edges": {
    "smooth": false
  },
  "physics": {
    "forceAtlas2Based": {
      "gravitationalConstant": -100,
      "centralGravity": 0.01,
      "springLength": 100,
      "springConstant": 0.08
    },
    "maxVelocity": 50,
    "solver": "forceAtlas2Based",
    "timestep": 0.35,
    "stabilization": {"iterations": 150}
  }
}
""")

html_path = os.path.expanduser("~/Desktop/cuyahoga_interactive.html")
net.save_graph(html_path)
print(f"✓ Saved HTML to {html_path}")
os.system(f"open {html_path}")
