import os, pickle, sys
import networkx as nx

sys.path.insert(0, os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/src"))

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

# Build the pure social graph
H = nx.Graph()
SOCIAL_RELS = {"married_to", "divorced_from", "litigated_with"}
for u, v, d in G.edges(data=True):
    if d.get("relation") in SOCIAL_RELS:
        if u.startswith("owner|") and v.startswith("owner|"):
            H.add_edge(u, v, **d)

print(f"Social Graph: {H.number_of_nodes():,} nodes, {H.number_of_edges():,} edges\n")

# Find the largest connected component
components = sorted(nx.connected_components(H), key=len, reverse=True)
H_cc = H.subgraph(components[0]).copy()
print(f"Largest social component: {H_cc.number_of_nodes():,} nodes\n")

# Calculate betweenness centrality (who bridges different clusters?)
print("Calculating betweenness centrality (this takes a few seconds)...")
bc = nx.betweenness_centrality(H_cc)

# Sort and print top 20
sorted_bc = sorted(bc.items(), key=lambda x: x[1], reverse=True)

print(f"{'Rank':<5} {'Name':<40} {'Score':<10} {'Degree'}")
print("-" * 75)
for i, (node, score) in enumerate(sorted_bc[:20], 1):
    name = node.replace("owner|", "")
    degree = H_cc.degree(node)
    print(f"{i:<5} {name:<40} {score:.4f}     {degree}")
