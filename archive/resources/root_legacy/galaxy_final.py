import os
import pandas as pd, igraph as ig, leidenalg, numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import warnings; warnings.filterwarnings("ignore")

CACHE = "fa2_positions.npy"
ITERATIONS = 200

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

# ---------- LAYOUT (with cache) ----------
if os.path.exists(CACHE):
    print(f"Loading cached FA2 positions from {CACHE}")
    pos = np.load(CACHE)
    if pos.shape[0] != g.vcount():
        print("  Cache mismatched node count, recomputing...")
        os.remove(CACHE)
        pos = None
else:
    pos = None

if pos is None:
    print(f"Calculating FA2 ({ITERATIONS} iterations, ~10 min)...")
    from pyforceatlas2 import ForceAtlas2
    fa = ForceAtlas2(
        outbound_attraction_distribution=False,
        lin_log_mode=True,
        barnes_hut_optimize=True,
        strong_gravity_mode=True,
        gravity=8.0,
        scaling_ratio=20.0,
    )
    nx_g = g.to_networkx()
    pos_dict = fa.forceatlas2_networkx_layout(nx_g, pos=None, iterations=ITERATIONS)
    # Robust key resolution: try name, then integer, then string-int
    pos = np.zeros((g.vcount(), 2))
    missing = 0
    for i in range(g.vcount()):
        name = g.vs[i]['name']
        if name in pos_dict:
            pos[i] = pos_dict[name]
        elif i in pos_dict:
            pos[i] = pos_dict[i]
        elif str(i) in pos_dict:
            pos[i] = pos_dict[str(i)]
        else:
            pos[i] = (0.0, 0.0)
            missing += 1
    if missing:
        print(f"  Warning: {missing} nodes had no position, placed at origin")
    np.save(CACHE, pos)
    print(f"  ✅ Saved positions to {CACHE} (future runs load instantly)")

x, y = pos[:,0], pos[:,1]

# ---------- COLORS ----------
distinct_20 = ['#e6194B','#3cb44b','#ffe119','#4363d8','#f58231','#911eb4',
               '#42d4f4','#f032e6','#bfef45','#fabed4','#469990','#dcbeff',
               '#9A6324','#fffac8','#800000','#aaffc3','#808000','#ffd8b1',
               '#000075','#a9a9a9']
color_map = {c: (distinct_20[r] if r < 20 else '#333333')
             for r, (s, c) in enumerate(comm_sizes)}

centroids = {}
for c_id in range(num_comms):
    nodes_in = [i for i in range(g.vcount()) if membership[i] == c_id]
    if nodes_in:
        centroids[c_id] = (np.mean(x[nodes_in]), np.mean(y[nodes_in]))

# ---------- RENDER ----------
print("Rendering...")
fig, ax = plt.subplots(figsize=(28, 28), facecolor='#0a0a0a')
ax.set_facecolor('#0a0a0a')

edges = np.array(g.get_edgelist())
intra = inter = 0
for u, v in edges:
    cu, cv = membership[u], membership[v]
    if cu == cv:
        ax.plot([x[u], x[v]], [y[u], y[v]], color=color_map.get(cu,'#333'),
                linewidth=0.12, alpha=0.18, zorder=1)
        intra += 1
    else:
        ax.plot([x[u], x[v]], [y[u], y[v]], color=color_map.get(cu,'#333'),
                linewidth=0.25, alpha=0.35, zorder=1)
        inter += 1
print(f"  Intra-community: {intra}, Inter-community: {inter}")

node_colors = [color_map.get(membership[i], '#333') for i in range(g.vcount())]
sizes = np.clip(degrees * 0.18 + betw_norm * 220, 3, 90)
ax.scatter(x, y, c=node_colors, s=sizes, alpha=0.95, edgecolors='none', zorder=2)

for size, c_id in comm_sizes[:20]:
    if size < 20 or c_id not in centroids: continue
    cx, cy = centroids[c_id]
    nodes_in = [i for i in range(g.vcount()) if membership[i] == c_id]
    hub = max(nodes_in, key=lambda n: degrees[n])
    ax.annotate(f"r/{names[hub]}", xy=(cx, cy), fontsize=12, color='white',
                ha='center', va='center', fontweight='bold', zorder=10,
                bbox=dict(boxstyle='round,pad=0.25', facecolor='black',
                          alpha=0.8, edgecolor=color_map.get(c_id, '#333'),
                          linewidth=1.5))

x_min, x_max = np.percentile(x, [1, 99])
y_min, y_max = np.percentile(y, [1, 99])
pad = 0.05
xr, yr = x_max - x_min, y_max - y_min
ax.set_xlim(x_min - pad*xr, x_max + pad*xr)
ax.set_ylim(y_min - pad*yr, y_max + pad*yr)
ax.set_aspect('equal')

legend_elems = [Line2D([0],[0], marker='o', color='w', label=f'{s}',
                        markerfacecolor='white',
                        markersize=np.sqrt(np.clip(s, 3, 90)/3))
                for s in [10, 40, 80]]
ax.legend(handles=legend_elems, loc='lower right', framealpha=0.85,
          facecolor='#1a1a1a', edgecolor='white', labelcolor='white',
          fontsize=13, title='Node size = degree + betweenness',
          title_fontsize=12)

ax.axis('off')
plt.tight_layout(pad=0)
plt.savefig("GALAXY_FINAL.png", dpi=200, bbox_inches='tight',
            facecolor='#0a0a0a', pad_inches=0)
print("✅ Saved GALAXY_FINAL.png")
