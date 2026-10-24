import os
os.environ['PYTHONHASHSEED'] = '0'
import pandas as pd, networkx as nx, numpy as np, random
from sklearn.metrics import average_precision_score
random.seed(42); np.random.seed(42)
def norm(e): return tuple(sorted(e))

df = pd.read_csv("soc-redditHyperlinks-body.tsv", sep='\t',
                 usecols=['SOURCE_SUBREDDIT','TARGET_SUBREDDIT','TIMESTAMP'])
df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'], utc=True)

def run(split_iso, n_hubs):
    split = pd.Timestamp(split_iso, tz="UTC")
    Gtr = nx.from_pandas_edgelist(df[df.TIMESTAMP<split],'SOURCE_SUBREDDIT','TARGET_SUBREDDIT',create_using=nx.Graph())
    Gte = nx.from_pandas_edgelist(df[df.TIMESTAMP>=split],'SOURCE_SUBREDDIT','TARGET_SUBREDDIT',create_using=nx.Graph())
    deg = dict(Gtr.degree())
    hubs = set(sorted(deg, key=deg.get, reverse=True)[:n_hubs]) if n_hubs else set()
    Gtr_strip = Gtr.copy(); Gtr_strip.remove_nodes_from(hubs)
    deg_strip = dict(Gtr_strip.degree())
    universe = set(sorted(deg_strip, key=deg_strip.get, reverse=True)[:2000])
    if not universe: return None

    nbr_full = {n: set(Gtr.neighbors(n)) for n in Gtr.nodes()}
    nbr_strip = {n: set(Gtr_strip.neighbors(n)) for n in Gtr_strip.nodes()}  # ALL nodes, fixed
    damp_full = {n: 1.0/np.log(max(2, deg[n]))       for n in Gtr.nodes()}
    damp_strip = {n: 1.0/np.log(max(2, deg_strip[n])) for n in Gtr_strip.nodes()}  # ALL nodes, fixed

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
    if len(pos) < 50: return None

    def aa_full(u,v):
        s = nbr_full.get(u,set()) & nbr_full.get(v,set())
        return sum(damp_full[w] for w in s) if s else 0.0
    def aa_strip(u,v):
        s = nbr_strip.get(u,set()) & nbr_strip.get(v,set())
        return sum(damp_strip[w] for w in s) if s else 0.0

    sc_f = np.array([aa_full(u,v) for u,v in cands])
    sc_s = np.array([aa_strip(u,v) for u,v in cands])
    y = np.array([1 if e in pos else 0 for e in cands])
    ap_f = average_precision_score(y, sc_f)
    ap_s = average_precision_score(y, sc_s)

    # Paired bootstrap
    d = []; idx_all = np.arange(len(y))
    for _ in range(300):
        idx = np.random.choice(idx_all, len(y), replace=True)
        yb = y[idx]
        if yb.sum()==0 or yb.sum()==len(yb): continue
        try: d.append(average_precision_score(yb, sc_s[idx]) - average_precision_score(yb, sc_f[idx]))
        except: pass
    d = np.array(d); lo, hi = np.percentile(d, [2.5, 97.5])
    return dict(split=split_iso, hubs=n_hubs, pool=len(cands), pos=len(pos),
                ap_s=ap_s, ap_f=ap_f, delta=ap_s-ap_f, lo=lo, hi=hi)

print(f"{'split':<12}{'hubs':>5}{'pool':>10}{'pos':>6}{'Δ AP':>10}{'95% CI':>24}")
results = []
for split in ["2015-07-01", "2016-01-01", "2016-07-01"]:
    for hubs in [0, 10, 50, 100, 300]:
        r = run(split, hubs)
        if r:
            results.append(r)
            print(f"{r['split']:<12}{r['hubs']:>5}{r['pool']:>10,}{r['pos']:>6}"
                  f"{r['delta']:>+10.4f}   [{r['lo']:+.4f}, {r['hi']:+.4f}]")

# Sanity: cutoff 0 must be exactly 0
zero_rows = [r for r in results if r['hubs']==0]
if zero_rows:
    all_zero = all(abs(r['delta']) < 1e-9 for r in zero_rows)
    print(f"\nSanity (hubs=0 should be 0.0000): {'PASS' if all_zero else 'FAIL'}")
