import pickle, os, networkx as nx
from networkx.algorithms import community
from pyvis.network import Network

print("Loading graph...")
G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

H = nx.Graph()
for u, v, d in G.edges(data=True):
    rel = d.get("relation", "")
    if u.startswith("owner|") and v.startswith("owner|"):
        H.add_edge(u, v, **d)
    elif rel == "same_mail" and u.startswith("owner|") and v.startswith("owner|"):
        H.add_edge(u, v, **d)

self_loops = list(nx.selfloop_edges(H))
H.remove_edges_from(self_loops)

print("Pruning graph to 2-core...")
core = nx.k_core(H, k=2)
top_nodes = sorted(core.degree, key=lambda x: x[1], reverse=True)[:4000]
H_sub = core.subgraph([n for n, d in top_nodes]).copy()
print(f"Visualizing top {H_sub.number_of_nodes()} nodes")

print("Detecting communities...")
communities = list(community.louvain_communities(H_sub, seed=42))
node_comm = {n: i for i, c in enumerate(communities) for n in c}
neon_colors = ["#ff5733", "#33ff57", "#3357ff", "#f333ff", "#33fff6", "#f6ff33", "#ff3369", "#8e44ad", "#e67e22", "#1abc9c"]

print("Building Vizpy HTML with Voter File cross-reference...")
net = Network(height="100vh", width="100%", bgcolor="#0a0a0a", font_color="#ffffff", directed=False, cdn_resources="in_line")

for n in H_sub.nodes():
    deg = H_sub.degree(n)
    size = 8 + (deg * 1.5)
    label = n.replace("owner|", "")
    
    # --- CROSS-REFERENCE WITH VOTER FILE ---
    nd = G.nodes[n]
    dob = nd.get("date_of_birth", "Unknown")
    addr = nd.get("residential_address", "Unknown")
    v_match = nd.get("voter_match", "none")
    
    # Build the rich tooltip
    tooltip = f"<b>{label}</b><br>DOB: {dob}<br>Address: {addr}<br>Voter Match: {v_match}"
    
    # If they have a voter match, they get their community color.
    # If they have no voter match, they are painted dark grey.
    if v_match in ("name_unique", "dob", "address"):
        bg_color = neon_colors[node_comm[n] % len(neon_colors)]
        border_color = "#ffffff"
    else:
        bg_color = "#444444" # Dark grey for unverified
        border_color = "#888888"
    
    net.add_node(n, label=label, size=size, 
                 color={"background": bg_color, "border": border_color}, 
                 title=tooltip, # THIS shows up on hover
                 font={"size": 14, "strokeWidth": 3, "strokeColor": "#000000", "face": "arial"})

for u, v, d in H_sub.edges(data=True):
    rel = d.get("relation", "")
    if rel in ["litigated_with", "mentioned_in_case"]:
        color = "#00ffff" # Cyan (Court)
        width = 1.5
    elif rel in ["married_to", "divorced_from"]:
        color = "#ff1493" # Pink (Marriage)
        width = 2.5
    elif rel == "same_mail":
        color = "#f1c40f" # Yellow (Property/Mail)
        width = 1.0
    else:
        color = "rgba(255, 255, 255, 0.2)" 
        width = 0.5
        
    net.add_edge(u, v, color=color, width=width, title=rel)

net.set_options("""
var options = {
  "nodes": {"borderWidth": 1, "borderWidthSelected": 2},
  "edges": {"smooth": false},
  "physics": {
    "barnesHut": {
      "gravitationalConstant": -300000,
      "centralGravity": 0.1,
      "springLength": 250,
      "springConstant": 0.02,
      "damping": 0.5,
      "avoidOverlap": 0.5
    },
    "solver": "barnesHut",
    "stabilization": {"iterations": 100}
  }
}
""")

html_path = os.path.expanduser("~/Desktop/cuyahoga_voter_crossref.html")
net.save_graph(html_path)
print(f"✓ Saved HTML to {html_path}")
os.system(f"open {html_path}")
