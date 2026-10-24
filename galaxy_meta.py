import os
import pandas as pd, igraph as ig, leidenalg, numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from adjustText import adjust_text
import warnings; warnings.filterwarnings("ignore")

CACHE = "meta_positions.npy"

print("Loading...")
df = pd.read_csv("soc-redditHyperlinks-body.tsv", sep='\t',
                 usecols=['SOURCE_SUBREDDIT','TARGET_SUBREDDIT']).drop_duplicates()
g = ig.Graph.TupleList(df.values.tolist(), directed=False)
g.delete_vertices(np.argsort(g.degree())[-100:])
g = g.k_core(4).components().giant()

print("Leiden communities...")
partition = leidenalg.find_partition(g, leidenalg.ModularityVertexPartition)
membership = partition.membership
comm_sizes = sorted([(len(c), i) for i, c in enumerate(partition)], reverse=True)

# Filter to top 25 communities
top_25_ids = set([c[1] for c in comm_sizes[:25]])
valid_nodes = [i for i in range(g.vcount()) if membership[i] in top_25_ids]
g = g.subgraph(valid_nodes)

# Recalculate
partition = leidenalg.find_partition(g, leidenalg.ModularityVertexPartition)
membership = partition.membership
comm_sizes = sorted([(len(c), i) for i, c in enumerate(partition)], reverse=True)

names = g.vs['name']
betw = np.array(g.betweenness(cutoff=2))
betw_norm = betw / max(betw.max(), 1)
degrees = np.array(g.degree())

critical_idx = np.argsort(betw)[-max(50, int(g.vcount() * 0.01)):]

# ============ LAYOUT ============
if os.path.exists(CACHE):
    final_pos = np.load(CACHE)
    if final_pos.shape[0] != g.vcount():
        os.remove(CACHE); final_pos = None
else:
    final_pos = None

if final_pos is None:
    print("Calculating Meta-graph Layout...")
    meta_edges = set()
    for u, v in g.get_edgelist():
        cu, cv = membership[u], membership[v]
        if cu != cv:
            meta_edges.add((min(cu, cv), max(cu, cv)))
    meta_g = ig.Graph(n=len(comm_sizes), edges=list(meta_edges))
    meta_pos = np.array(meta_g.layout_fruchterman_reingold(niter=500).coords) 
    if np.max(np.abs(meta_pos)) > 0:
        # Scale up the meta-graph so communities are spread out
        meta_pos = (meta_pos / np.max(np.abs(meta_pos))) * 200 
    final_pos = np.zeros((g.vcount(), 2))
    for c_id in range(len(comm_sizes)):
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

x, y = final_pos[:,0], final_pos[:,1]
x = x * 1.4
y = y * 1.4

# ============ COLORS ============
distinct_20 = ['#e6194B','#3cb44b','#ffe119','#4363d8','#f58231','#911eb4',
               '#42d4f4','#f032e6','#bfef45','#fabed4','#469990','#dcbeff',
               '#9A6324','#fffac8','#800000','#aaffc3','#808000','#ffd8b1',
               '#000075','#a9a9a9']
color_map = {c: (distinct_20[r] if r < 20 else '#333333')
             for r, (s, c) in enumerate(comm_sizes)}

# ============ RENDER ============
print("Rendering...")
fig, ax = plt.subplots(figsize=(40, 40), facecolor='#0a0a0a')
ax.set_facecolor('#0a0a0a')

edges = np.array(g.get_edgelist())
for u, v in edges:
    cu, cv = membership[u], membership[v]
    edge_color = color_map.get(cu, '#333333')
    crit = max(betw_norm[u], betw_norm[v])
    
    if cu == cv:
        if crit > 0.5: lw, alpha = 0.60, 0.65
        elif crit > 0.2: lw, alpha = 0.20, 0.25
        else: lw, alpha = 0.06, 0.10
        ax.plot([x[u], x[v]], [y[u], y[v]], color=edge_color, linewidth=lw, alpha=alpha, zorder=1)
    else:
        mid_x = (x[u] + x[v]) / 2 + np.random.normal(0, 0.8)
        mid_y = (y[u] + y[v]) / 2 + np.random.normal(0, 0.8)
        if crit > 0.5: lw, alpha = 0.50, 0.55
        else: lw, alpha = 0.10, 0.15
        ax.plot([x[u], mid_x, x[v]], [y[u], mid_y, y[v]], color=edge_color, linewidth=lw, alpha=alpha, zorder=1)

node_colors = [color_map.get(membership[i], '#333') for i in range(g.vcount())]
sizes = np.clip(degrees * 0.1 + (betw_norm ** 0.8) * 800, 4, 400)

ax.scatter(x, y, c=node_colors, s=sizes, alpha=0.95, edgecolors='none', zorder=2)

crit_colors = [node_colors[i] for i in critical_idx]
ax.scatter(x[critical_idx], y[critical_idx], c=crit_colors, s=sizes[critical_idx], 
           alpha=1.0, edgecolors='#ffffff', linewidths=3.0, zorder=15)

# ============ LABELS ============
labeled_nodes = set()
texts = []

# 1. ELITE: Top 10 by Degree OR Top 10 by Betweenness (Red)
elite_indices = list(set(np.argsort(degrees)[-10:]) | set(np.argsort(betw)[-10:]))
for idx in elite_indices:
    labeled_nodes.add(idx)
    t = ax.text(x[idx], y[idx], f"r/{names[idx]}", fontsize=10, color='white',
                ha='center', va='center', fontweight='bold', zorder=20, clip_on=True,
                bbox=dict(boxstyle='round,pad=0.1', facecolor='#e6194B',
                          alpha=0.95, edgecolor='#ffffff', linewidth=0.8))
    texts.append(t)

# 2. EVERY WHITE HALO NODE (Black)
for idx in critical_idx:
    if idx in labeled_nodes: continue
    labeled_nodes.add(idx)
    t = ax.text(x[idx], y[idx], f"r/{names[idx]}", fontsize=8, color='white',
                ha='center', va='center', fontweight='bold', zorder=18, clip_on=True,
                bbox=dict(boxstyle='round,pad=0.1', facecolor='#111111',
                          alpha=0.9, edgecolor='#ffffff', linewidth=0.6))
    texts.append(t)

# 3. ISLAND HUBS
for size, c_id in comm_sizes:
    nodes_in = [i for i in range(g.vcount()) if membership[i] == c_id]
    sub = g.subgraph(nodes_in)
    hub_local_idx = max(range(len(nodes_in)), key=lambda i: sub.degree(i))
    hub_idx = nodes_in[hub_local_idx]
    
    if hub_idx in labeled_nodes: continue
    
    labeled_nodes.add(hub_idx)
    t = ax.text(x[hub_idx], y[hub_idx], f"r/{names[hub_idx]}", fontsize=8, color='white',
                ha='center', va='center', fontweight='bold', zorder=18, clip_on=True,
                bbox=dict(boxstyle='round,pad=0.1', facecolor='#111111',
                          alpha=0.9, edgecolor='#ffffff', linewidth=0.6))
    texts.append(t)

# 4. Repel labels
print(f"Repelling {len(texts)} labels...")
adjust_text(texts, 
            x=x, y=y, 
            arrowprops=dict(arrowstyle='-', color='#aaaaaa', lw=0.5, shrinkA=2, shrinkB=2),
            expand_points=(2.0, 2.0),
            expand_text=(1.5, 1.5),
            force_text=(5.0, 5.0), 
            force_points=(1.0, 1.0), 
            time_lim=30,              
            lim=500)

# ============ CROP (THE FIX) ============
# Use 0.5% to 99.5% to include the top cluster but ignore the extreme rogue nodes
x_min, x_max = np.percentile(x, [0.5, 99.5])
y_min, y_max = np.percentile(y, [0.5, 99.5])
xr, yr = x_max - x_min, y_max - y_min
pad = 0.10
ax.set_xlim(x_min - pad*xr, x_max + pad*xr)
ax.set_ylim(y_min - pad*yr, y_max + pad*yr)
ax.set_aspect('equal')

# ============ LEGEND ============
legend_elems = [
    Line2D([0],[0], marker='o', color='w', label='Elite (Top 10)', markerfacecolor='#e6194B', markersize=10),
    Line2D([0],[0], marker='o', color='w', label='Critical Node', markerfacecolor='#e6194B', markeredgecolor='white', markeredgewidth=1.5, markersize=8),
    Line2D([0],[0], marker='o', color='w', label='Island Hub', markerfacecolor='#111111', markeredgecolor='white', markeredgewidth=1, markersize=10)
]
ax.legend(handles=legend_elems, loc='upper left', framealpha=0.9,
          facecolor='#1a1a1a', edgecolor='white', labelcolor='white',
          fontsize=10, title='Legend', title_fontsize=12)

ax.axis('off')
plt.savefig("GALAXY_META.png", dpi=200, facecolor='#0a0a0a', pad_inches=0)
print("✅ Saved GALAXY_META.png")
