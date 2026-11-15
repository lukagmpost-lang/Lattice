import pickle, os, networkx as nx
from networkx.algorithms import community
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import random

print("Loading graph...")
G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

# Extract social graph
H = nx.Graph()
for u, v, d in G.edges(data=True):
    if d.get("relation") in {"married_to", "divorced_from", "litigated_with"}:
        if u.startswith("owner|") and v.startswith("owner|"):
            H.add_edge(u, v)

print(f"Total social graph: {H.number_of_nodes()} nodes, {H.number_of_edges()} edges")

# 1. Communities
print("Detecting communities...")
communities = list(community.louvain_communities(H, seed=42))
node_comm = {}
for i, c in enumerate(communities):
    for n in c:
        node_comm[n] = i

colors = list(mcolors.CSS4_COLORS.values())
random.seed(42)
random.shuffle(colors)
node_colors = {n: colors[node_comm[n] % len(colors)] for n in H.nodes()}

# 2. Layout (Tightly Packed)
print("Calculating tightly packed layout (this will take 5-10 minutes)...")
# We use a very small k (repulsion) so it packs tightly like a galaxy
pos = nx.spring_layout(H, k=0.02, iterations=30, seed=42)

# 3. Render PNG
print("Drawing massive image...")
fig, ax = plt.subplots(figsize=(200, 200), dpi=150) # 200x200 inches, massive resolution

# Draw edges first (faint)
nx.draw_networkx_edges(H, pos, ax=ax, alpha=0.1, edge_color="#555555", width=0.5)

# Draw all nodes
nx.draw_networkx_nodes(H, pos, ax=ax, node_size=2, 
                       node_color=[node_colors[n] for n in H.nodes()], edgecolors="none")

# Draw ALL labels
nx.draw_networkx_labels(H, pos, labels={n: n.replace("owner|", "") for n in H.nodes()}, 
                        ax=ax, font_size=1, font_weight="normal", font_color="black", alpha=0.8)

ax.axis("off")
plt.tight_layout()

png_path = os.path.expanduser("~/Desktop/cuyahoga_full_packed.png")
pdf_path = os.path.expanduser("~/Desktop/cuyahoga_full_packed.pdf")

print("Saving files (this will take a minute)...")
plt.savefig(png_path, bbox_inches="tight")
plt.savefig(pdf_path, format="pdf", bbox_inches="tight")

print(f"✓ Saved PNG to {png_path}")
print(f"✓ Saved PDF to {pdf_path}")
os.system(f"open {pdf_path}")
