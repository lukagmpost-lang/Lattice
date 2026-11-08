import os, pickle, sys
import networkx as nx

def run():
    G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
    H = nx.Graph()
    for u, v, d in G.edges(data=True):
        if d.get("relation") in {"married_to", "divorced_from", "litigated_with", "mentioned_in_case"}:
            if u.startswith("owner|") and v.startswith("owner|"):
                H.add_edge(u, v, **d)

    print(f"Social Graph: {H.number_of_nodes():,} nodes, {H.number_of_edges():,} edges")
    if H.number_of_nodes() == 0:
        return

    components = sorted(nx.connected_components(H), key=len, reverse=True)
    H_cc = H.subgraph(components[0]).copy()
    print(f"Largest social component: {H_cc.number_of_nodes():,} nodes\n")
    
    bc = nx.betweenness_centrality(H_cc)
    sorted_bc = sorted(bc.items(), key=lambda x: x[1], reverse=True)
    
    print(f"{'Rank':<5} {'Name':<40} {'Score':<10} {'Degree'}")
    print("-" * 75)
    for i, (node, score) in enumerate(sorted_bc[:20], 1):
        print(f"{i:<5} {node.replace('owner|', ''):<40} {score:.4f}     {H_cc.degree(node)}")

if __name__ == "__main__":
    run()
