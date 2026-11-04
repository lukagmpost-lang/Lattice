import os, pickle, sys
import networkx as nx

sys.path.insert(0, os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/src"))
from osi.viz import render_interactive_html

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
print(f"loaded: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

H = nx.Graph()
SOCIAL_RELS = {"married_to", "divorced_from", "litigated_with"}

for u, v, d in G.edges(data=True):
    if d.get("relation") in SOCIAL_RELS:
        if u.startswith("owner|") and v.startswith("owner|"):
            H.add_edge(u, v, **d)

print(f"social subgraph: {H.number_of_nodes():,} nodes, {H.number_of_edges():,} edges")

if H.number_of_nodes() == 0:
    print("No social edges found.")
    sys.exit()

components = sorted(nx.connected_components(H), key=len, reverse=True)
print(f"social components: {len(components)}")
print(f"largest social component: {len(components[0]):,} nodes")
H_cc = H.subgraph(components[0]).copy()

for n in H_cc.nodes():
    if H_cc.degree(n) > 3:
        H_cc.nodes[n]["size"] = 20 + H_cc.degree(n) * 2
    else:
        H_cc.nodes[n]["size"] = 10

out = os.path.expanduser("~/Desktop/cuyahoga_social_graph.html")
render_interactive_html(H_cc, out, min_edge_weight=1, top_labels=200)
print(f"wrote {out}")
