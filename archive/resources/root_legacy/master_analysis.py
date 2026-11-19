import pandas as pd
import igraph as ig
import leidenalg
import networkx as nx
import numpy as np
import random
import warnings
warnings.filterwarnings("ignore")

print("Loading Reddit Hyperlink Network...")
df = pd.read_csv("soc-redditHyperlinks-body.tsv", sep='\t', usecols=['SOURCE_SUBREDDIT', 'TARGET_SUBREDDIT']).drop_duplicates()

g = ig.Graph.TupleList(df.values.tolist(), directed=True)
nxg = nx.from_pandas_edgelist(df, 'SOURCE_SUBREDDIT', 'TARGET_SUBREDDIT', create_using=nx.DiGraph())
g_undir = g.as_undirected()
nxg_undir = nxg.to_undirected()

report = ["# Master Network Analysis Report\n"]
report.append(f"**Network Size:** {g.vcount()} Nodes | {g.ecount()} Edges\n")
names = g.vs['name']

def top_5(items):
    return "\n".join([f"- **{name}**: {score:.5f}" for name, score in items])

# 1. PageRank
print("[1/7] PageRank...")
pr = g.pagerank()
report.append("## 1. Centrality")
report.append("### PageRank (Overall Influence)\n" + top_5(sorted(zip(names, pr), key=lambda x: x[1], reverse=True)[:5]))

# 2. HITS
print("[2/7] HITS...")
hubs, auths = g.hub_score(), g.authority_score()
report.append("\n### HITS Authorities (Best Content)\n" + top_5(sorted(zip(names, auths), key=lambda x: x[1], reverse=True)[:5]))

# 3. Betweenness
print("[3/7] Betweenness...")
betw = g.betweenness(cutoff=2)
report.append("\n### Betweenness (The Bridges)\n" + top_5(sorted(zip(names, betw), key=lambda x: x[1], reverse=True)[:5]))

# 4. Top 500 subgraph + Burt Constraint
print("[4/7] Selecting top 500 hubs...")
top_nodes = sorted(enumerate(g.degree()), key=lambda x: x[1], reverse=True)[:100]
top_names = [g.vs[i]['name'] for i, deg in top_nodes]
nxg_top = nxg.subgraph(top_names)
print(f"   Subgraph: {nxg_top.number_of_nodes()} nodes, {nxg_top.number_of_edges()} edges")
print(f"   Subgraph: {nxg_top.number_of_nodes()} nodes, {nxg_top.number_of_edges()} edges")

print("[5/7] Burt Constraint (structural holes)...")
try:
    constraint = nx.constraint(nxg_top)
    report.append("\n## 2. Structural Holes")
    report.append("### Burt's Constraint (Lowest = Best Brokers)")
    report.append(top_5(sorted(constraint.items(), key=lambda x: x[1])[:5]))
    print("   Done")
except Exception as e:
    print(f"   Failed: {e}")

# 5. Communities
print("[6/7] Community Detection...")
report.append("\n## 3. Community Detection")
try:
    louvain = g_undir.community_multilevel()
    report.append(f"- Louvain: {len(louvain)} communities (Modularity: {louvain.modularity:.4f})")
except Exception: pass
try:
    leiden = leidenalg.find_partition(g_undir, leidenalg.ModularityVertexPartition)
    report.append(f"- Leiden: {len(leiden)} communities (Modularity: {leiden.modularity:.4f})")
except Exception: pass

# 6. Health
report.append("\n## 4. Network Health")
art_points = list(nx.articulation_points(nxg_undir))
report.append(f"- Articulation Points: {len(art_points)} nodes")
report.append(f"- Assortativity: {nx.degree_assortativity_coefficient(nxg_undir):.4f}")
report.append(f"- Clustering Coefficient: {nx.average_clustering(nxg_undir):.4f}")

# 7. Robustness
print("[7/7] Robustness + Link Prediction...")
report.append("\n## 5. Robustness")
report.append("| Strategy | 1% | 5% | 10% | 20% | 30% |")
report.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

def simulate(graph, strategy, pcts=[0.01, 0.05, 0.10, 0.20, 0.30]):
    results = []
    orig = graph.vcount()
    for p in pcts:
        n = int(orig * p)
        tg = graph.copy()
        if strategy == "random":
            rm = np.random.choice(tg.vcount(), n, replace=False)
        elif strategy == "degree":
            rm = np.argsort(tg.degree())[-n:]
        tg.delete_vertices(rm)
        results.append(f"{tg.components().giant().vcount()/orig*100:.1f}%")
    return " | ".join(results)

report.append(f"| Random | {simulate(g_undir, 'random')} |")
report.append(f"| Degree-First | {simulate(g_undir, 'degree')} |")

# Link Prediction
report.append("\n## 6. Link Prediction")
def fmt(preds, title):
    res = sorted(preds, key=lambda x: x[2], reverse=True)[:5]
    return f"### {title}\n" + "\n".join([f"- **r/{u}** <--> **r/{v}**: {p:.4f}" for u, v, p in res])

report.append(fmt(nx.adamic_adar_index(nxg_top), "Adamic-Adar"))
report.append(fmt(nx.resource_allocation_index(nxg_top), "Resource Allocation"))

with open("ULTIMATE_FINDINGS.md", "w", encoding="utf-8") as f:
    f.write("\n".join(report))

print("\n✅ COMPLETE. Saved to ULTIMATE_FINDINGS.md")
