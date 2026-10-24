import os
os.environ['PYTHONHASHSEED'] = '0'
import pandas as pd, networkx as nx, numpy as np
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

# Candidate pool: 2-hop in FULL graph, universe-internal endpoints
nbr = {n: set(Gtr.neighbors(n)) for n in Gtr.nodes()}
nbr_strip = {n: set(Gtr_strip.neighbors(n)) for n in universe if n in Gtr_strip}
damp_full = {n: 1.0/np.log(max(2, deg[n])) for n in Gtr.nodes()}
damp_strip = {n: 1.0/np.log(max(2, deg_strip[n])) for n in deg_strip}

print("Building candidate pool...")
cands = set()
for u, ns in nbr.items():
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
print(f"Pool: {len(cands):,}  Positives: {len(pos):,}\n")

def aa_full(u, v):
    s = nbr.get(u, set()) & nbr.get(v, set())
    return sum(damp_full[w] for w in s if w in damp_full) if s else 0.0
def aa_strip(u, v):
    s = nbr_strip.get(u, set()) & nbr_strip.get(v, set())
    return sum(damp_strip[w] for w in s if w in damp_strip) if s else 0.0

# Score both ways on same pool
sc_f = np.array([aa_full(u,v) for u,v in cands])
sc_s = np.array([aa_strip(u,v) for u,v in cands])

# Top-100 by each scoring graph
top_f_set = set(np.lexsort((np.arange(len(sc_f)), -sc_f))[:100])
top_s_set = set(np.lexsort((np.arange(len(sc_s)), -sc_s))[:100])

# Percentile-rank endpoints by degree (0-100)
deg_sorted = np.array(sorted(deg.values()))
def deg_pct(n):
    return 100.0 * np.searchsorted(deg_sorted, deg.get(n, 0)) / len(deg_sorted)

groups = {
    "Only in AA_full top-100":  top_f_set - top_s_set,
    "Only in AA_strip top-100": top_s_set - top_f_set,
    "In both top-100s":         top_f_set & top_s_set,
}

print(f"{'group':<30}{'n':>5}{'hits':>7}{'hit%':>8}{'med_upct':>10}{'med_vpct':>10}")
print("-"*72)
for name, g in groups.items():
    if not g: 
        print(f"{name:<30}{0:>5}")
        continue
    hits = sum(1 for i in g if cands[i] in pos)
    upcts = [deg_pct(cands[i][0]) for i in g]
    vpcts = [deg_pct(cands[i][1]) for i in g]
    print(f"{name:<30}{len(g):>5}{hits:>7}{hits/len(g)*100:>7.1f}%"
          f"{np.median(upcts):>10.1f}{np.median(vpcts):>10.1f}")

# Inspect the full-only and strip-only pairs
for name, g in [("ONLY IN AA_full", top_f_set - top_s_set),
                ("ONLY IN AA_strip", top_s_set - top_f_set)]:
    print(f"\n{name}:")
    for i in sorted(g, key=lambda x: -sc_f[x] if name=="ONLY IN AA_full" else -sc_s[x])[:10]:
        u, v = cands[i]
        hit = '✅' if cands[i] in pos else '❌'
        print(f"  {u:<22}  {v:<22}  "
              f"full={sc_f[i]:6.2f} (deg% {deg_pct(u):5.0f}/{deg_pct(v):5.0f})  "
              f"strip={sc_s[i]:6.2f}  {hit}")

print("\n" + "="*72)
print("DIAGNOSIS")
print("="*72)
full_only = groups["Only in AA_full top-100"]
strip_only = groups["Only in AA_strip top-100"]
if full_only and strip_only:
    f_hits = sum(1 for i in full_only if cands[i] in pos) / len(full_only)
    s_hits = sum(1 for i in strip_only if cands[i] in pos) / len(strip_only)
    f_deg = np.median([max(deg_pct(cands[i][0]), deg_pct(cands[i][1])) for i in full_only])
    s_deg = np.median([max(deg_pct(cands[i][0]), deg_pct(cands[i][1])) for i in strip_only])
    print(f"  Full-only pairs: hit {f_hits*100:.0f}%  median endpoint degree percentile {f_deg:.0f}")
    print(f"  Strip-only pairs: hit {s_hits*100:.0f}%  median endpoint degree percentile {s_deg:.0f}")
    if f_hits < s_hits and f_deg > s_deg:
        print("  → CONFIRMED: full-scorer top-100 promotes large-endpoint pairs that miss;")
        print("    strip-scorer top-100 surfaces smaller-endpoint pairs that hit.")
    elif f_hits < s_hits:
        print("  → PARTIAL: strip-only hit rate higher, but endpoint-size diff is small.")
    else:
        print("  → NOT CONFIRMED: strip-only pairs don't hit more than full-only pairs.")
