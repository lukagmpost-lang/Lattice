import os
os.environ['PYTHONHASHSEED'] = '0'
import pandas as pd, networkx as nx, numpy as np
from sklearn.metrics import average_precision_score
def norm(e): return tuple(sorted(e))

df = pd.read_csv("soc-redditHyperlinks-body.tsv", sep='\t',
                 usecols=['SOURCE_SUBREDDIT','TARGET_SUBREDDIT','TIMESTAMP'])
df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'], utc=True)
split = pd.Timestamp("2016-01-01", tz="UTC")
Gtr = nx.from_pandas_edgelist(df[df.TIMESTAMP<split],'SOURCE_SUBREDDIT','TARGET_SUBREDDIT',create_using=nx.Graph())
Gte = nx.from_pandas_edgelist(df[df.TIMESTAMP>=split],'SOURCE_SUBREDDIT','TARGET_SUBREDDIT',create_using=nx.Graph())

deg = dict(Gtr.degree())
hubs = set(sorted(deg, key=deg.get, reverse=True)[:100])
Gtr_strip = Gtr.copy(); Gtr_strip.remove_nodes_from(hubs)
deg_strip = dict(Gtr_strip.degree())
universe = set(sorted(deg_strip, key=deg_strip.get, reverse=True)[:2000])

# Candidate pool — built ONCE from full graph, used by all three scorers below
nbr_full = {n: set(Gtr.neighbors(n)) for n in Gtr.nodes()}
cands = set()
for u, ns in nbr_full.items():
    uni = sorted(x for x in ns if x in universe)
    for i in range(len(uni)):
        for j in range(i+1, len(uni)):
            a, b = uni[i], uni[j]
            if not Gtr.has_edge(a, b):
                cands.add(norm((a, b)))
cands = sorted(cands)
train_e = set(norm(e) for e in Gtr.subgraph(universe).edges())
new_e = set()
for u, v in Gte.edges():
    if u in universe and v in universe:
        e = norm((u, v))
        if e not in train_e: new_e.add(e)
pos = set(cands) & new_e
y = np.array([1 if e in pos else 0 for e in cands])
print(f"Pool: {len(cands):,}  Positives: {len(pos):,}\n")

# ---- Three scorers ----
# 1. "full": Gtr, damp on all nodes
damp_full = {n: 1.0/np.log(max(2, deg[n])) for n in Gtr.nodes()}
def aa_full(u, v):
    s = nbr_full.get(u, set()) & nbr_full.get(v, set())
    return sum(damp_full[w] for w in s) if s else 0.0

# 2. "strip0": literally the same graph as full (hubs=0), so should match #1 exactly
nbr_strip0 = {n: set(Gtr.neighbors(n)) for n in Gtr.nodes()}  # same Gtr
damp_strip0 = {n: 1.0/np.log(max(2, deg[n])) for n in Gtr.nodes()}  # same deg
def aa_strip0(u, v):
    s = nbr_strip0.get(u, set()) & nbr_strip0.get(v, set())
    return sum(damp_strip0[w] for w in s) if s else 0.0

# 3. "strip100": Gtr with top-100 hubs removed, damp on remaining nodes
nbr_strip100 = {n: set(Gtr_strip.neighbors(n)) for n in Gtr_strip.nodes()}
damp_strip100 = {n: 1.0/np.log(max(2, deg_strip[n])) for n in Gtr_strip.nodes()}
def aa_strip100(u, v):
    s = nbr_strip100.get(u, set()) & nbr_strip100.get(v, set())
    return sum(damp_strip100[w] for w in s) if s else 0.0

# ---- Identity check: strip0 MUST equal full ----
print("=" * 60)
print("HUB=0 IDENTITY CHECK")
print("=" * 60)
sc_f  = np.array([aa_full(u,v)   for u,v in cands])
sc_s0 = np.array([aa_strip0(u,v) for u,v in cands])
identical = np.array_equal(sc_f, sc_s0)
ap_f  = average_precision_score(y, sc_f)
ap_s0 = average_precision_score(y, sc_s0)
delta0 = ap_s0 - ap_f
print(f"Scores identical at hubs=0: {'YES' if identical else 'NO'}")
print(f"AP_full   = {ap_f:.10f}")
print(f"AP_strip0 = {ap_s0:.10f}")
print(f"Δ AP      = {delta0:.10e}   {'PASS' if delta0 == 0.0 else 'FAIL — non-zero delta at hubs=0'}")

# ---- Real comparison at hubs=100 ----
print("\n" + "=" * 60)
print("MAIN COMPARISON (hubs=100)")
print("=" * 60)
sc_s100 = np.array([aa_strip100(u,v) for u,v in cands])
ap_s100 = average_precision_score(y, sc_s100)

def p100(sc):
    order = np.lexsort((np.arange(len(sc)), -sc))[:100]
    return int(y[order].sum())

print(f"AA_full    P@100 = {p100(sc_f):3d}/100   AP = {ap_f:.4f}")
print(f"AA_strip   P@100 = {p100(sc_s100):3d}/100   AP = {ap_s100:.4f}")
print(f"Δ AP (strip − full) = {ap_s100 - ap_f:+.4f}")
