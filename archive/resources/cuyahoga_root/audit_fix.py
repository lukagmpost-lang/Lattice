import os, pickle, networkx as nx

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_transfers.pkl"), "rb"))
print(f"loaded: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

ex = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_graph.pkl"), "rb"))
ex_owners = {n[6:] for n in ex.nodes if n.startswith("owner|")}

gs = set(u for u,_ in G.out_degree)
gt = set(v for v,_ in G.in_degree)
all_n = gs | gt
names = {n[6:] for n in all_n if isinstance(n, str) and n.startswith("owner|")}
ov = names & ex_owners

print("\n1. OVERLAP")
print(f"   grantors: {len(gs):,}")
print(f"   grantees: {len(gt):,}")
print(f"   total:    {len(all_n):,}")
print(f"   overlap:  {len(ov):,} ({100*len(ov)/max(1,len(names)):.1f}%)")

ws = [d["weight"] for _,_,d in G.edges(data=True)]
nm = sum(1 for w in ws if w > 1)
print("\n3. WEIGHT")
print(f"   edges: {len(ws):,}")
print(f"   >1:    {nm:,} ({100*nm/max(1,len(ws)):.1f}%)")
print(f"   max:   {max(ws) if ws else 0:,}")
print(f"   mean:  {sum(ws)/len(ws):.2f}" if ws else "")

print("\n4. TOP GRANTORS (sold to N distinct)")
for n,d in sorted(G.out_degree, key=lambda x:-x[1])[:15]:
    p = sum(G[n][t]["weight"] for t in G.successors(n))
    print(f"   {d:5d} buyers, {p:6d} parcels  {n[6:][:70]}")

print("\nTOP GRANTEES (bought from N distinct)")
for n,d in sorted(G.in_degree, key=lambda x:-x[1])[:15]:
    p = sum(G[s][n]["weight"] for s in G.predecessors(n))
    print(f"   {d:5d} sellers, {p:6d} parcels  {n[6:][:70]}")

print("\nTOP VOLUME (parcels moved, either direction)")
vol = {}
for u,v,d in G.edges(data=True):
    w = d["weight"]
    vol[u] = vol.get(u,0) + w
    vol[v] = vol.get(v,0) + w
for n,c in sorted(vol.items(), key=lambda x:-x[1])[:10]:
    print(f"   {c:6d} parcels  {n[6:][:70]}")
