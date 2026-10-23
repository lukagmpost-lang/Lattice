import pandas as pd
import igraph as ig
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import matplotlib

print("Parsing TSV file...")
df = pd.read_csv("soc-redditHyperlinks-body.tsv", sep='\t', usecols=['SOURCE_SUBREDDIT', 'TARGET_SUBREDDIT'])
df_unique = df.drop_duplicates()
g = ig.Graph.TupleList(df_unique.values.tolist(), directed=False)

print("1. Removing top 100 mega-hubs...")
degrees = g.degree()
top_hubs = np.argsort(degrees)[-100:]
g.delete_vertices(top_hubs)

print("2. Aggressive Pruning (K-Core = 4)...")
g = g.k_core(4)
g = g.components().giant()
print(f"Core Graph: {g.vcount()} nodes, {g.ecount()} edges.")

print("3. Calculating Betweenness Centrality...")
betweenness = np.array(g.betweenness()) 

print("4. Detecting communities (Louvain)...")
communities = g.community_multilevel()
membership = communities.membership
num_comms = len(communities)

print("5. Calculating 3D Meta-Graph Layout...")
meta_g = ig.Graph(n=num_comms)
meta_edges = set()
for u, v in g.get_edgelist():
    cu, cv = membership[u], membership[v]
    if cu != cv:
        meta_edges.add((min(cu, cv), max(cu, cv)))
meta_g.add_edges(list(meta_edges))

# dim=3 tells igraph to calculate in 3D space
meta_layout = meta_g.layout_fruchterman_reingold(niter=1000, dim=3)
meta_coords = np.array(meta_layout.coords)

# Normalize macro layout to a sphere of radius 100
if np.max(np.abs(meta_coords)) > 0:
    meta_coords = (meta_coords / np.max(np.abs(meta_coords))) * (num_comms * 2)

print("6. Calculating 3D Intra-cluster Layout...")
final_coords = np.zeros((g.vcount(), 3))

for comm_id in range(num_comms):
    nodes_in_comm = [i for i in range(g.vcount()) if membership[i] == comm_id]
    if len(nodes_in_comm) == 0: continue
        
    if len(nodes_in_comm) > 1:
        subg = g.subgraph(nodes_in_comm)
        local_layout = subg.layout_fruchterman_reingold(niter=100, dim=3)
        local_coords = np.array(local_layout.coords)
        if np.max(np.abs(local_coords)) > 0:
            local_coords = (local_coords / np.max(np.abs(local_coords))) * 5
    else:
        local_coords = np.zeros((1, 3))
        
    for idx, node_id in enumerate(nodes_in_comm):
        final_coords[node_id, 0] = meta_coords[comm_id, 0] + local_coords[idx, 0]
        final_coords[node_id, 1] = meta_coords[comm_id, 1] + local_coords[idx, 1]
        final_coords[node_id, 2] = meta_coords[comm_id, 2] + local_coords[idx, 2]

print("7. Projecting onto a Sphere (Virus Capsid effect)...")
# Center the graph
center = np.mean(final_coords, axis=0)
final_coords -= center

# Normalize every node to lie exactly on the surface of a sphere (Radius = 100)
radii = np.linalg.norm(final_coords, axis=1)
radii[radii == 0] = 1
sphere_coords = (final_coords / radii[:, None]) * 100

# Rotate the sphere for a dynamic 3D perspective
theta = np.radians(30)
phi = np.radians(20)
R_y = np.array([[np.cos(theta), 0, np.sin(theta)], [0, 1, 0], [-np.sin(theta), 0, np.cos(theta)]])
R_x = np.array([[1, 0, 0], [0, np.cos(phi), -np.sin(phi)], [0, np.sin(phi), np.cos(phi)]])
rotated = np.dot(sphere_coords, np.dot(R_y, R_x).T)

# Project to 2D
x = rotated[:, 0]
y = rotated[:, 1]
z_depth = rotated[:, 2]

print("8. Rendering 3D Virus Capsid Image...")
fig, ax = plt.subplots(figsize=(30, 30), facecolor='#000000')
ax.set_facecolor('#000000')

# Sort edges by depth (back edges drawn first)
edges = np.array(g.get_edgelist())
edge_depths = (z_depth[edges[:, 0]] + z_depth[edges[:, 1]]) / 2
sort_idx = np.argsort(edge_depths)
edges = edges[sort_idx]
lines = [[(x[e[0]], y[e[0]]), (x[e[1]], y[e[1]])] for e in edges]

# Draw edges with varying transparency based on depth
for i, line in enumerate(lines):
    depth = edge_depths[sort_idx[i]]
    # Map depth to alpha: 0.02 (back) to 0.4 (front)
    alpha = 0.02 + 0.38 * ((depth - np.min(z_depth)) / (np.max(z_depth) - np.min(z_depth)))
    ax.plot([line[0][0], line[1][0]], [line[0][1], line[1][1]], 
            color='#ffffff', linewidth=0.4, alpha=alpha, zorder=1)

# Sort nodes by depth (front nodes drawn last)
node_sort_idx = np.argsort(z_depth)

cmap = matplotlib.colormaps['tab20'].resampled(num_comms)
max_b = np.max(betweenness) if np.max(betweenness) > 0 else 1
sizes = 5 + (betweenness / max_b) * 200

for idx in node_sort_idx:
    depth = z_depth[idx]
    # Front nodes are slightly bigger and fully opaque
    depth_scale = 0.6 + 0.4 * ((depth - np.min(z_depth)) / (np.max(z_depth) - np.min(z_depth)))
    size = sizes[idx] * depth_scale
    alpha = 0.5 + 0.5 * ((depth - np.min(z_depth)) / (np.max(z_depth) - np.min(z_depth)))
    
    ax.scatter(x[idx], y[idx], c=[cmap(membership[idx])], s=size, 
               alpha=alpha, edgecolors='white', linewidths=0.5, zorder=2)

# LABELS (Only on the front-facing nodes)
print("Adding labels...")
comm_sizes = [(len(c), i) for i, c in enumerate(communities)]
comm_sizes.sort(reverse=True)
top_15_comms = [c[1] for c in comm_sizes[:15]]

for comm_id in top_15_comms:
    nodes_in_comm = [i for i in range(g.vcount()) if membership[i] == comm_id]
    hub_node = max(nodes_in_comm, key=lambda n: betweenness[n])
    
    # Only label if it's on the front half of the sphere
    if z_depth[hub_node] > 0:
        hub_name = g.vs[hub_node]["name"]
        ax.annotate(f"r/{hub_name}", 
                    xy=(x[hub_node], y[hub_node]), 
                    xytext=(10, 10),
                    textcoords='offset points',
                    color='white', fontsize=14, fontweight='bold', fontfamily='sans-serif',
                    bbox=dict(facecolor='black', alpha=0.8, edgecolor='#ffaa00', boxstyle='round,pad=0.3'),
                    arrowprops=dict(arrowstyle='-', color='#ffaa00', lw=1.5),
                    zorder=10)

ax.autoscale()
ax.axis('off')
plt.tight_layout(pad=0)

output_filename = "reddit_galaxy_sphere.png"
plt.savefig(output_filename, dpi=300, bbox_inches='tight', facecolor='#000000', pad_inches=0)
print(f"✅ Success! Image saved as '{output_filename}'")
