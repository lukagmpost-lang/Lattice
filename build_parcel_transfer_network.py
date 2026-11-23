#!/usr/bin/env python3
"""
High-Value Parcel Transfer Network Generator

Builds: Cluster A -> Parcel -> Cluster B graph from:
  - Raw transfers JSON: parcel_id, grantor, grantee, book_page, amount, date
  - Resolved clusters: cuyahoga_resolved_clusters.parquet (owner|NAME -> cluster_id)
  - Unified graph: parcel situs addresses

Filters: total_amount > $50,000 AND (at least one cluster confidence = HIGH)
Outputs: 
  - PNG visualization (HIGH-confidence only)
  - Full network GraphML (all 570 matched edges)
  - CSV of top 20 flipped parcels
"""

import json
import pickle
import re
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from collections import defaultdict, Counter

def normalize_name(name: str) -> str:
    """Normalize name for matching: strip, uppercase, collapse spaces. KEEP owner| prefix."""
    if not name:
        return ''
    return re.sub(r'\s+', ' ', name.strip().upper())

def split_grantees(grantee: str) -> list[str]:
    """Split compound grantee on '&' and normalize each."""
    parts = [normalize_name(p) for p in grantee.split('&')]
    return [p for p in parts if p]

# ============================================================
# 1. LOAD RESOLVED CLUSTERS
# ============================================================
print("Loading cuyahoga_resolved_clusters.parquet...")
clusters_df = pd.read_parquet('cuyahoga_resolved_clusters.parquet')

owner_to_cluster = dict(zip(
    clusters_df['node_id'].astype(str).apply(normalize_name),
    clusters_df['cluster_id']
))
cluster_confidence = clusters_df.drop_duplicates('cluster_id').set_index('cluster_id')['confidence_level'].to_dict()
cluster_label = clusters_df.drop_duplicates('cluster_id').set_index('cluster_id')['full_name'].to_dict()

print(f"  {len(owner_to_cluster):,} owners mapped to clusters")
print(f"  {len(cluster_confidence):,} unique clusters")

# ============================================================
# 2. BUILD PARCEL LOOKUP FROM RAW JSON
# ============================================================
print("Loading cuyahoga_transfers_raw.json (for parcel_id)...")
with open('/Users/2950639/Desktop/cuyahoga_transfers_raw.json', 'r') as f:
    raw_data = json.load(f)

parcel_lookup = {}
for feat in raw_data['features']:
    a = feat.get('attributes', {})
    grantor = 'OWNER|' + normalize_name(a.get('grantor', ''))
    grantee_full = 'OWNER|' + normalize_name(a.get('grantee', ''))
    book_page = normalize_name(a.get('book_page', ''))
    parcel_id = a.get('parcel_id', '').strip()
    if not (grantor and parcel_id):
        continue
    for grantee in split_grantees(grantee_full):
        key = (grantor, grantee, book_page)
        parcel_lookup[key] = parcel_id

print(f"  {len(parcel_lookup):,} parcel mappings from raw JSON")

# Parcel situs from unified graph
print("Loading cuyahoga_unified.pkl for parcel situs...")
with open('/Users/2950639/Desktop/cuyahoga_unified.pkl', 'rb') as f:
    unified = pickle.load(f)

parcel_situs = {}
for node, data in unified.nodes(data=True):
    if data.get('type') == 'parcel':
        parcel_situs[f"parcel|{data.get('pid', '')}"] = data.get('situs', '')

print(f"  {len(parcel_situs):,} parcels with situs addresses")

# ============================================================
# 3. LOAD TRANSFER GRAPH AND MATCH TO PARCELS
# ============================================================
print("Loading cuyahoga_transfers.pkl...")
with open('/Users/2950639/Desktop/cuyahoga_transfers.pkl', 'rb') as f:
    transfers = pickle.load(f)

high_conf_edges = []      # at least one cluster HIGH
all_matched_edges = []    # all 570 matched edges
parcel_flip_pairs = defaultdict(set)

matched_total = 0
matched_high = 0

for source, target, tdata in transfers.edges(data=True):
    amount = tdata.get('total_amount', 0)
    if amount <= 50000:
        continue
    
    source = str(source)
    target = str(target)
    
    source_norm = normalize_name(source)
    target_norm = normalize_name(target)
    
    cluster_a = owner_to_cluster.get(source_norm)
    cluster_b = owner_to_cluster.get(target_norm)
    
    if cluster_a is None or cluster_b is None:
        continue
    if cluster_a == cluster_b:
        continue
    
    conf_a = cluster_confidence.get(cluster_a, 'LOW')
    conf_b = cluster_confidence.get(cluster_b, 'LOW')
    is_high_conf = (conf_a == 'HIGH' or conf_b == 'HIGH')
    
    book_pages = tdata.get('book_pages', [])
    parcel_id = None
    matched_bp = ''
    for bp in book_pages:
        bp_clean = normalize_name(bp)
        key = (source_norm, target_norm, bp_clean)
        if key in parcel_lookup:
            parcel_id = parcel_lookup[key]
            matched_bp = bp_clean
            break
    
    if not parcel_id:
        continue
    
    matched_total += 1
    edge_data = {
        'cluster_a': cluster_a,
        'cluster_b': cluster_b,
        'label_a': cluster_label.get(cluster_a, f'cluster:{cluster_a}'),
        'label_b': cluster_label.get(cluster_b, f'cluster:{cluster_b}'),
        'parcel': parcel_id,
        'situs': parcel_situs.get(f'parcel|{parcel_id}', ''),
        'amount': amount,
        'date': tdata.get('first_date', ''),
        'reference': matched_bp,
        'weight': tdata.get('weight', 1),
        'n_transactions': tdata.get('n_transactions', 1),
        'conf_a': conf_a,
        'conf_b': conf_b,
    }
    all_matched_edges.append(edge_data)
    parcel_flip_pairs[parcel_id].add((cluster_a, cluster_b))
    
    if is_high_conf:
        matched_high += 1
        high_conf_edges.append(edge_data)

print(f"\n  Total matched transfers with parcels: {matched_total}")
print(f"  With at least one HIGH-confidence cluster: {matched_high}")
print(f"  All LOW-confidence: {matched_total - matched_high}")

# ============================================================
# 4. BUILD NETWORKX GRAPHS
# ============================================================
def build_graph(edges, name):
    H = nx.DiGraph()
    clusters_in = set()
    for e in edges:
        clusters_in.add(e['cluster_a'])
        clusters_in.add(e['cluster_b'])
    for cid in clusters_in:
        H.add_node(f"cluster:{cid}", 
                   label=cluster_label.get(cid, f'Cluster {cid}'),
                   type='cluster',
                   confidence=cluster_confidence.get(cid, 'LOW'),
                   cluster_id=cid)
    for e in edges:
        parcel_node = f"parcel|{e['parcel']}"
        if parcel_node not in H:
            H.add_node(parcel_node,
                       label=e['situs'][:50] if e['situs'] else parcel_node,
                       type='parcel',
                       situs=e['situs'],
                       parcel_id=e['parcel'])
        H.add_edge(f"cluster:{e['cluster_a']}", parcel_node,
                   cluster_a=e['cluster_a'], cluster_b=e['cluster_b'],
                   amount=e['amount'], date=e['date'], reference=e['reference'],
                   weight=e['weight'], n_transactions=e['n_transactions'],
                   direction='out')
        H.add_edge(parcel_node, f"cluster:{e['cluster_b']}",
                   cluster_a=e['cluster_a'], cluster_b=e['cluster_b'],
                   amount=e['amount'], date=e['date'], reference=e['reference'],
                   weight=e['weight'], n_transactions=e['n_transactions'],
                   direction='in')
    print(f"  {name}: {H.number_of_nodes()} nodes, {H.number_of_edges()} edges")
    return H

print("\nBuilding HIGH-confidence network...")
H_high = build_graph(high_conf_edges, "HIGH-confidence")

print("Building full matched network...")
H_all = build_graph(all_matched_edges, "Full matched")

# ============================================================
# 5. TOP 20 FLIPPED PARCELS CSV
# ============================================================
flip_counts = {p: len(pairs) for p, pairs in parcel_flip_pairs.items()}
top20 = sorted(flip_counts.items(), key=lambda x: -x[1])[:20]

csv_rows = []
for parcel, flip_count in top20:
    total_amt = sum(e['amount'] for e in all_matched_edges if e['parcel'] == parcel)
    clusters_involved = set()
    for e in all_matched_edges:
        if e['parcel'] == parcel:
            clusters_involved.add(e['cluster_a'])
            clusters_involved.add(e['cluster_b'])
    csv_rows.append({
        'parcel_id': parcel,
        'situs': parcel_situs.get(f'parcel|{parcel}', ''),
        'flip_count': flip_count,
        'distinct_clusters': len(clusters_involved),
        'total_volume': total_amt,
        'avg_amount': total_amt / flip_count if flip_count else 0,
        'clusters': '; '.join(str(c) for c in clusters_involved),
    })

csv_df = pd.DataFrame(csv_rows)
csv_df.to_csv('top20_flipped_parcels.csv', index=False)
print(f"\nTop 20 flipped parcels written to top20_flipped_parcels.csv")
if len(csv_df) > 0:
    print(csv_df[['parcel_id', 'flip_count', 'distinct_clusters', 'total_volume', 'situs']].to_string(index=False))

# ============================================================
# 6. RENDER PNGs
# ============================================================
def render_png(H, output_path, title_suffix):
    if H.number_of_nodes() == 0:
        print(f"  {output_path}: No data to visualize")
        return
    
    print(f"\nRendering {output_path}...")
    pos = nx.kamada_kawai_layout(H, scale=2.0)
    
    cluster_nodes = [n for n, d in H.nodes(data=True) if d.get('type') == 'cluster']
    parcel_nodes = [n for n, d in H.nodes(data=True) if d.get('type') == 'parcel']
    
    fig, ax = plt.subplots(figsize=(24, 24), facecolor='#0f0f1a')
    ax.set_facecolor('#0f0f1a')
    
    edge_colors = []
    edge_widths = []
    for u, v, d in H.edges(data=True):
        amt = d.get('amount', 50000)
        edge_colors.append('#00d4aa' if d.get('direction') == 'out' else '#008866')
        edge_widths.append(0.5 + min(amt / 100000, 3.0))
    
    nx.draw_networkx_edges(H, pos, edge_color=edge_colors, width=edge_widths,
                           alpha=0.35, arrows=True, arrowsize=10, arrowstyle='-|>', ax=ax)
    
    nx.draw_networkx_nodes(H, pos, nodelist=parcel_nodes, node_color='#ffaa00',
                           node_size=80, node_shape='s', edgecolors='#ffcc44',
                           linewidths=0.8, alpha=0.9, ax=ax, label='Parcel')
    
    cluster_sizes = [100 + H.degree(n) * 30 for n in cluster_nodes]
    cluster_colors = ['#00d4aa' if H.nodes[n].get('confidence') == 'HIGH' else '#ff6b6b' 
                      for n in cluster_nodes]
    cluster_borders = ['#00ffcc' if H.nodes[n].get('confidence') == 'HIGH' else '#ff9999'
                       for n in cluster_nodes]
    
    for i, n in enumerate(cluster_nodes):
        nx.draw_networkx_nodes(H, pos, nodelist=[n], node_color=cluster_colors[i],
                               node_size=cluster_sizes[i], node_shape='o',
                               edgecolors=cluster_borders[i], linewidths=1.2,
                               alpha=0.95, ax=ax)
    
    top_parcel_nodes = sorted(parcel_nodes, key=lambda n: H.degree(n), reverse=True)[:30]
    label_nodes = cluster_nodes + top_parcel_nodes
    labels = {n: H.nodes[n].get('label', n) for n in label_nodes}
    
    nx.draw_networkx_labels(H, pos, labels=labels, font_size=7,
                            font_color='#eaeaea', font_weight='bold', ax=ax)
    
    ax.set_title(
        f'High-Value Parcel Transfer Network\n'
        f'Cluster -> Parcel -> Cluster | Amount > $50K | {title_suffix}',
        fontsize=18, color='#eaeaea', pad=20
    )
    
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#00d4aa', markeredgecolor='#00ffcc',
               markersize=12, label='HIGH-Confidence Cluster', markeredgewidth=1.2),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#ff6b6b', markeredgecolor='#ff9999',
               markersize=12, label='LOW-Confidence Cluster', markeredgewidth=1.2),
        Line2D([0], [0], marker='s', color='w', markerfacecolor='#ffaa00', markeredgecolor='#ffcc44',
               markersize=10, label='Parcel', markeredgewidth=0.8),
        Line2D([0], [0], color='#00d4aa', lw=2, label='Transfer Out'),
        Line2D([0], [0], color='#008866', lw=2, label='Transfer In'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=11,
              facecolor='#1a1a2e', edgecolor='#444', labelcolor='#eaeaea')
    ax.axis('off')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, facecolor='#0f0f1a', bbox_inches='tight')
    print(f"  PNG saved to {output_path}")

# Render HIGH-confidence only
render_png(H_high, 'high_value_parcel_transfer_network_high_conf.png', 'Confidence = HIGH (at least one)')

# Render full network
render_png(H_all, 'high_value_parcel_transfer_network_full.png', 'All Matched Transfers')

# Save GraphMLs
nx.write_graphml(H_high, 'high_value_parcel_network_high_conf.graphml')
nx.write_graphml(H_all, 'high_value_parcel_network_full.graphml')
print("\nGraphML files saved.")

print("\nDone!")
