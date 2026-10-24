import os
os.environ['PYTHONHASHSEED'] = '0'
import pandas as pd, networkx as nx, numpy as np
from collections import Counter
def norm(e): return tuple(sorted(e))

df = pd.read_csv("soc-redditHyperlinks-body.tsv", sep='\t',
                 usecols=['SOURCE_SUBREDDIT','TARGET_SUBREDDIT','TIMESTAMP'])
df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'], utc=True)
split = pd.Timestamp("2016-01-01", tz="UTC")
Gtr = nx.from_pandas_edgelist(df[df.TIMESTAMP<split],'SOURCE_SUBREDDIT','TARGET_SUBREDDIT',create_using=nx.Graph())
Gte = nx.from_pandas_edgelist(df[df.TIMESTAMP>=split],'SOURCE_SUBREDDIT','TARGET_SUBREDDIT',create_using=nx.Graph())

deg = dict(Gtr.degree())
hubs_100 = set(sorted(deg, key=deg.get, reverse=True)[:100])
Gtr_strip = Gtr.copy(); Gtr_strip.remove_nodes_from(hubs_100)
deg_strip = dict(Gtr_strip.degree())
universe = set(sorted(deg_strip, key=deg_strip.get, reverse=True)[:2000])

train_e = set(norm(e) for e in Gtr.subgraph(universe).edges())
new_e = set()
for u, v in Gte.edges():
    if u in universe and v in universe:
        e = norm((u, v))
        if e not in train_e: new_e.add(e)

nbr = {n: set(Gtr.neighbors(n)) for n in Gtr.nodes()}
damp = {n: 1.0/np.log(max(2, deg[n])) for n in Gtr.nodes()}

# Same candidate pool as union_pool_v2 (2-hop in FULL graph)
print("Building union 2-hop candidates...")
cands = set()
for u, ns in nbr.items():
    uni = sorted(x for x in ns if x in universe)
    for i in range(len(uni)):
        for j in range(i+1, len(uni)):
            a, b = uni[i], uni[j]
            if not Gtr.has_edge(a, b):
                cands.add(norm((a, b)))
cands = sorted(cands)
pos = set(cands) & new_e
print(f"Pool: {len(cands):,}  Positives: {len(pos):,}\n")

def score(u, v):
    s = nbr.get(u, set()) & nbr.get(v, set())
    return sum(damp[w] for w in s if w in damp) if s else 0.0

sc = np.array([score(u, v) for u, v in cands])
y  = np.array([1 if e in pos else 0 for e in cands])
order = np.lexsort((np.arange(len(sc)), -sc))

# --- For top-100 pairs, inspect shared neighbors ---
print("=" * 90)
print("INSPECT TOP-100 AA PREDICTIONS (hubs=0, i.e., full graph scoring)")
print("=" * 90)
print(f"{'rank':<5}{'u':<22}{'v':<22}{'AA':>6} {'hit':<4}{'shared_mega_hub?'}")
mega_shared = 0
any_hub_shared = 0
for rank, idx in enumerate(order[:100], 1):
    u, v = cands[idx]
    shared = nbr.get(u, set()) & nbr.get(v, set())
    shared_hubs = shared & hubs_100
    hit = '✅' if norm((u, v)) in pos else '❌'
    # A "mega-hub flood" means the shared neighbor set is dominated by top-100 hubs
    if shared_hubs:
        any_hub_shared += 1
        if len(shared_hubs) == len(shared):
            mega_shared += 1
            marker = 'YES (only shared nbr is a hub)'
        else:
            marker = f'partial ({len(shared_hubs)}/{len(shared)} shared nbrs are hubs)'
    else:
        marker = 'no'
    if rank <= 25:
        print(f"{rank:<5}{u:<22}{v:<22}{sc[idx]:>6.2f} {hit:<4}{marker}")

print(f"\nOf top-100 predictions:")
print(f"  - pairs whose ONLY shared neighbors are top-100 hubs: {mega_shared}/100")
print(f"  - pairs that share at least one top-100 hub:          {any_hub_shared}/100")

# --- Compare to base rate ---
all_pairs_hub_shared = sum(1 for u, v in cands
                           if (nbr.get(u,set()) & nbr.get(v,set()) & hubs_100))
print(f"  - base rate of 'shares a top-100 hub':                {all_pairs_hub_shared/len(cands)*100:.1f}% of pool")

# --- What are the top-ranked shared hubs by frequency? ---
hub_count = Counter()
for idx in order[:100]:
    u, v = cands[idx]
    shared = nbr.get(u, set()) & nbr.get(v, set())
    for h in (shared & hubs_100):
        hub_count[h] += 1
print(f"\nTop shared hubs in top-100 predictions:")
for h, c in hub_count.most_common(10):
    print(f"  r/{h:<25} appears as shared neighbor in {c}/100 top predictions")

print("\n" + "=" * 90)
print("DIAGNOSIS")
print("=" * 90)
if mega_shared > 50:
    print("⚠ CONFIRMED: majority of top-100 predictions share ONLY mega-hubs.")
    print("  The 'mega-hub flood' hypothesis is true. AA_strip's advantage is real.")
    print("  At hubs=0, the top-100 are dominated by hub-coincidence pairs that don't convert.")
elif any_hub_shared > 50:
    print("PARTIAL: majority share at least one hub but not exclusively.")
    print("  Hub presence matters but isn't the whole story.")
else:
    print("NOT SUPPORTED: top-100 predictions do NOT overwhelmingly share mega-hubs.")
    print("  The high-AP at hubs=0 cannot be explained by mega-hub flooding.")
