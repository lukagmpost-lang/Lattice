import networkx as nx

def compute_snap_algorithms(G: nx.DiGraph):
    metrics = {}

    # 1. HITS
    try:
        hubs, authorities = nx.hits(G, max_iter=500)
        metrics["top_hubs"] = sorted(hubs.items(), key=lambda x: x[1], reverse=True)[:10]
        metrics["top_authorities"] = sorted(authorities.items(), key=lambda x: x[1], reverse=True)[:10]
    except Exception as e:
        print(f"HITS failed: {e}")

    # 2. In/Out Degree
    in_deg = nx.in_degree_centrality(G)
    out_deg = nx.out_degree_centrality(G)
    metrics["top_in_degree"] = sorted(in_deg.items(), key=lambda x: x[1], reverse=True)[:10]
    metrics["top_out_degree"] = sorted(out_deg.items(), key=lambda x: x[1], reverse=True)[:10]

    # 3. Eigenvector
    try:
        eigen = nx.eigenvector_centrality(G, max_iter=1000)
        metrics["top_eigenvector"] = sorted(eigen.items(), key=lambda x: x[1], reverse=True)[:10]
    except Exception as e:
        print(f"Eigenvector failed: {e}")

    # 4. Reciprocity
    metrics["reciprocity"] = nx.overall_reciprocity(G)

    # 5. Edge Betweenness (Sampled)
    try:
        edge_betweenness = nx.edge_betweenness_centrality(G, k=500, weight=None)
        metrics["top_bridge_edges"] = sorted(edge_betweenness.items(), key=lambda x: x[1], reverse=True)[:10]
    except Exception as e:
        print(f"Edge betweenness failed: {e}")

    # 6. K-Core
    try:
        core_numbers = nx.core_number(G)
        metrics["top_core_nodes"] = sorted(core_numbers.items(), key=lambda x: x[1], reverse=True)[:10]
    except Exception as e:
        print(f"K-core failed: {e}")

    print("✅ Algorithms computed successfully.")
    return metrics
