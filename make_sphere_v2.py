import pandas as pd, igraph as ig, leidenalg, numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import warnings; warnings.filterwarnings("ignore")

print("Loading...")
df = pd.read_csv("soc-redditHyperlinks-body.tsv", sep='\t',
                 usecols=['SOURCE_SUBREDDIT','TARGET_SUBREDDIT']).drop_duplicates()
g = ig.Graph.TupleList(df.values.tolist(), directed=False)
g.delete_vertices(np.argsort(g.degree())[-100:])
g = g.k_core(4).components().giant()
print(f"Graph: {g.vcount()} nodes, {g.ecount()} edges")
names = g.vs['name']

print("Leiden...")
partition = leidenalg.find_partition(g, leidenalg.ModularityVertexPartition)
membership = partition.membership
num_comms = len(partition)
comm_sizes = sorted([(len(c), i) for i, c in enumerate(partition)], reverse=True)

# Distinct palette
distinct_20 = ['#e6194B','#3cb44b','#ffe119','#4363d8','#f58231','#911eb4',
               '#42d4f4','#f032e6','#bfef45','#fabed4','#469990','#dcbeff',
               '#9A6324','#fffac8','#800000','#aaffc3','#808000','#ffd8b1',
               '#000075','#a9a9a9']
color_map = {c: (distinct_20[r] if r < 20 else '#333333')
             for r, (s, c) in enumerate(comm_sizes)}

print("3D Meta-Graph layout...")
meta_edges = list({(min(membership[u],membership[v]), max(membership[u],membership[v]))
                   for u,v in g.get_edgelist() if membership[u]!=membership[v]})
meta_g = ig.Graph(n=num_comms, edges=meta_edges)
meta_pos = np.array(meta_g.layout_fruchterman_reingold(niter=500, dim=3).coords)
if np.max(np.abs(meta_pos)) > 0:
    meta_pos = (meta_pos / np.max(np.abs(meta_pos))) * (num_comms * 2)

print("3D Intra-cluster layout...")
final = np.zeros((g.vcount(), 3))
for c in range(num_comms):
    nodes = [i for i in range(g.vcount()) if membership[i] == c]
    if not nodes: continue
    if len(nodes) > 1:
        loc = np.array(g.subgraph(nodes).layout_fruchterman_reingold(niter=100, dim=3).coords)
        if np.max(np.abs(loc)) > 0:
            loc = (loc / np.max(np.abs(loc))) * 5
    else:
        loc = np.zeros((1, 3))
    for i, n in enumerate(nodes):
        final[n] = meta_pos[c] + loc[i]

print("Projecting onto sphere...")
final -= final.mean(axis=0)
r = np.linalg.norm(final, axis=1); r[r==0] = 1
sphere = (final / r[:, None]) * 100

# Rotate
th, ph = np.radians(30), np.radians(20)
Ry = np.array([[np.cos(th),0,np.sin(th)],[0,1,0],[-np.sin(th),0,np.cos(th)]])
Rx = np.array([[1,0,0],[0,np.cos(ph),-np.sin(ph)],[0,np.sin(ph),np.cos(ph)]])
rot = sphere @ (Ry @ Rx).T
x, y, z = rot[:,0], rot[:,1], rot[:,2]
degrees = np.array(g.degree())

print("Rendering...")
fig, ax = plt.subplots(figsize=(28, 28), facecolor='#0a0a0a')
ax.set_facecolor('#0a0a0a')

# ONLY inter-community edges, colored by source community, thin + faint
edges = np.array(g.get_edgelist())
edge_depths = (z[edges[:,0]] + z[edges[:,1]]) / 2
order = np.argsort(edge_depths)
zmin, zmax = z.min(), z.max()
zr = max(zmax - zmin, 1)

drawn = 0
for idx in order:
    u, v = edges[idx]
    cu, cv = membership[u], membership[v]
    if cu == cv: continue
    depth = edge_depths[idx]
    depth_norm = (depth - zmin) / zr
    alpha = 0.02 + 0.12 * depth_norm     # 0.02 back -> 0.14 front
    ax.plot([x[u], x[v]], [y[u], y[v]],
            color=color_map.get(cu, '#333'),
            linewidth=0.15, alpha=alpha, zorder=1)
    drawn += 1
print(f"  Inter-community edges: {drawn} / {len(edges)}")

# Nodes with depth sorting
node_colors = [color_map.get(membership[i], '#333') for i in range(g.vcount())]
sizes = np.clip(degrees * 0.35, 4, 45)
for i in np.argsort(z):
    dn = (z[i] - zmin) / zr
    alpha = 0.55 + 0.45 * dn
    s = sizes[i] * (0.65 + 0.35 * dn)
    ax.scatter(x[i], y[i], c=[node_colors[i]], s=s, alpha=alpha,
               edgecolors='white', linewidths=0.3, zorder=2)

# Labels at cluster centroids (only front-facing)
centroids = {}
for c_id in range(num_comms):
    nodes_in = [i for i in range(g.vcount()) if membership[i] == c_id]
    if not nodes_in: continue
    cx, cy, cz = x[nodes_in].mean(), y[nodes_in].mean(), z[nodes_in].mean()
    centroids[c_id] = (cx, cy, cz)

for size, c_id in comm_sizes[:20]:
    if c_id not in centroids: continue
    cx, cy, cz = centroids[c_id]
    if cz < 0: continue          # skip back-of-sphere labels
    nodes_in = [i for i in range(g.vcount()) if membership[i] == c_id]
    hub = max(nodes_in, key=lambda n: degrees[n])
    ax.annotate(f"r/{names[hub]}", xy=(cx, cy), fontsize=12, color='white',
                ha='center', va='center', fontweight='bold', zorder=10,
                bbox=dict(boxstyle='round,pad=0.25', facecolor='black',
                          alpha=0.85, edgecolor=color_map.get(c_id, '#333'),
                          linewidth=1.5))

# Legend
legend_elems = [Line2D([0],[0], marker='o', color='w', label=f'{s}+ links',
                        markerfacecolor='white',
                        markersize=np.sqrt(np.clip(s*0.35, 4, 45)))
                for s in [3, 10, 25]]
ax.legend(handles=legend_elems, loc='lower right', framealpha=0.85,
          facecolor='#1a1a1a', edgecolor='white', labelcolor='white',
          fontsize=13, title='Node size = degree', title_fontsize=13)

ax.set_xlim(-115, 115)
ax.set_ylim(-115, 115)
ax.set_aspect('equal')
ax.axis('off')
plt.tight_layout(pad=0)
plt.savefig("reddit_sphere_v2.png", dpi=200, bbox_inches='tight',
            facecolor='#0a0a0a', pad_inches=0)
print("✅ Saved reddit_sphere_v2.png")
