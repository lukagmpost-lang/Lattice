import os
import pandas as pd, igraph as ig, leidenalg, numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import warnings; warnings.filterwarnings("ignore")

CACHE = "meta_positions.npy"

print("Loading...")
df = pd.read_csv("soc-redditHyperlinks-body.tsv", sep='\t',
                 usecols=['SOURCE_SUBREDDIT','TARGET_SUBREDDIT']).drop_duplicates()
g = ig.Graph.TupleList(df.values.tolist(), directed=False)
g.delete_vertices(np.argsort(g.degree())[-100:])
g = g.k_core(4).components().giant()
print(f"Graph: {g.vcount()} nodes, {g.ecount()} edges")
names = g.vs['name']

print("Leiden communities...")
partition = leidenalg.find_partition(g, leidenalg.ModularityVertexPartition)
membership = partition.membership
num_comms = len(partition)
comm_sizes = sorted([(len(c), i) for i, c in enumerate(partition)], reverse=True)

print("Betweenness...")
betw = np.array(g.betweenness(cutoff=2))
betw_norm = betw / max(betw.max(), 1)
degrees = np.array(g.degree())

# ============ META-GRAPH LAYOUT (cached) ============
if os.path.exists(CACHE):
    print(f"Loading cached positions...")
    final_pos = np.load(CACHE)
    if final_pos.shape[0] != g.vcount():
        os.remove(CACHE); final_pos = None
else:
    final_pos = None

if final_pos is None:
    print("1. Meta-graph FR layout...")
    meta_edges = set()
    for u, v in g.get_edgelist():
        cu, cv = membership[u], membership[v]
        if cu != cv:
            meta_edges.add((min(cu, cv), max(cu, cv)))
    meta_g = ig.Graph(n=num_comms, edges=list(meta_edges))
    meta_pos = np.array(meta_g.layout_fruchterman_reingold(niter=1000).coords)
    if np.max(np.abs(meta_pos)) > 0:
        meta_pos = (meta_pos / np.max(np.abs(meta_pos))) * 100

    print("2. Per-community FR layout...")
    final_pos = np.zeros((g.vcount(), 2))
    for c_id in range(num_comms):
        nodes = [i for i in range(g.vcount()) if membership[i] == c_id]
        if not nodes: continue
        if len(nodes) == 1:
            final_pos[nodes[0]] = meta_pos[c_id]; continue
        sub = g.subgraph(nodes)
        local = np.array(sub.layout_fruchterman_reingold(niter=150).coords)
        if np.max(np.abs(local)) > 0:
            radius = 3 + np.sqrt(len(nodes)) * 0.4
            local = (local / np.max(np.abs(local))) * radius
        for i, n in enumerate(nodes):
            final_pos[n] = meta_pos[c_id] + local[i]
    np.save(CACHE, final_pos)
    print(f"  ✅ Cached")

x, y = final_pos[:,0], final_pos[:,1]

# ============ COLORS ============
distinct_20 = ['#e6194B','#3cb44b','#ffe119','#4363d8','#f58231','#911eb4',
               '#42d4f4','#f032e6','#bfef45','#fabed4','#469990','#dcbeff',
               '#9A6324','#fffac8','#800000','#aaffc3','#808000','#ffd8b1',
               '#000075','#a9a9a9']
color_map = {c: (distinct_20[r] if r < 20 else '#333333')
             for r, (s, c) in enumerate(comm_sizes)}

# ============ RENDER ============
print("Rendering with criticality-weighted edges...")
fig, ax = plt.subplots(figsize=(28, 28), facecolor='#0a0a0a')
ax.set_facecolor('#0a0a0a')

edges = np.array(g.get_edgelist())
intra = inter = 0

# Draw edges in 4 tiers by criticality
for u, v in edges:
    cu, cv = membership[u], membership[v]
    edge_color = color_map.get(cu, '#333333')
    crit = max(betw_norm[u], betw_norm[v])

    if cu == cv:
        # INTRA-CLUSTER: straight lines radiating from hub
        if crit > 0.5:
            lw, alpha = 0.55, 0.55       # bright rays from critical nodes
        elif crit > 0.2:
            lw, alpha = 0.20, 0.25       # medium
        else:
            lw, alpha = 0.06, 0.08       # barely visible background
        ax.plot([x[u], x[v]], [y[u], y[v]], color=edge_color,
                linewidth=lw, alpha=alpha, zorder=1)
        intra += 1
    else:
        # INTER-CLUSTER: curved (jittered) so spine doesn't reappear
        mid_x = (x[u] + x[v]) / 2 + np.random.normal(0, 0.8)
        mid_y = (y[u] + y[v]) / 2 + np.random.normal(0, 0.8)
        if crit > 0.5:
            lw, alpha = 0.40, 0.45
        else:
            lw, alpha = 0.12, 0.18
        ax.plot([x[u], mid_x, x[v]], [y[u], mid_y, y[v]], color=edge_color,
                linewidth=lw, alpha=alpha, zorder=1)
        inter += 1

print(f"  Intra: {intra}, Inter: {inter}")

# ============ NODES: criticality-amplified sizes ============
node_colors = [color_map.get(membership[i], '#333') for i in range(g.vcount())]
# Exponential scaling on betweenness so top 1% are unmistakable
sizes = np.clip(degrees * 0.12 + (betw_norm ** 0.7) * 500, 4, 300)

# Draw regular nodes first
ax.scatter(x, y, c=node_colors, s=sizes, alpha=0.95, edgecolors='none', zorder=2)

# Draw top 1% critical nodes with a white halo ON TOP
critical_idx = np.argsort(betw)[-max(50, int(g.vcount() * 0.01)):]
crit_colors = [node_colors[i] for i in critical_idx]
ax.scatter(x[critical_idx], y[critical_idx], c=crit_colors,
           s=sizes[critical_idx], alpha=1.0,
           edgecolors='#ffffff', linewidths=2.5, zorder=15)

# ============ LABELS ============
for size, c_id in comm_sizes[:20]:
    if size < 50: continue
    nodes_in = [i for i in range(g.vcount()) if membership[i] == c_id]
    hub = max(nodes_in, key=lambda n: betw[n])  # label by highest BETWEENNESS, not degree
    ax.annotate(f"r/{names[hub]}", xy=(x[hub], y[hub]), xytext=(15, -8),
                textcoords='offset points', fontsize=13, color='white',
                ha='left', va='bottom', fontweight='bold', zorder=20,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='black',
                          alpha=0.9, edgecolor='#ffffff', linewidth=1.2))

# ============ CROP ============
x_min, x_max = np.percentile(x, [2, 98])
y_min, y_max = np.percentile(y, [2, 98])
pad = 0.05
xr, yr = x_max - x_min, y_max - y_min
ax.set_xlim(x_min - pad*xr, x_max + pad*xr)
ax.set_ylim(y_min - pad*yr, y_max + pad*yr)
ax.set_aspect('equal')

legend_elems = [Line2D([0],[0], marker='o', color='w', label=f'{s}',
                        markerfacecolor='white',
                        markersize=np.sqrt(np.clip(s, 4, 300)/3))
                for s in [10, 40, 100, 200]]
ax.legend(handles=legend_elems, loc='lower right', framealpha=0.85,
          facecolor='#1a1a1a', edgecolor='white', labelcolor='white',
          fontsize=13, title='Node size = degree + betweenness',
          title_fontsize=12)

ax.axis('off')
plt.tight_layout(pad=0)
plt.savefig("GALAXY_META.png", dpi=200, bbox_inches='tight',
            facecolor='#0a0a0a', pad_inches=0)
print("✅ Saved GALAXY_META.png")
