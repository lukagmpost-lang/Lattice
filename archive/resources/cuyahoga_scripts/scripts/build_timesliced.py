import json, os, pickle, re
from collections import defaultdict
import networkx as nx

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

raw = [f["attributes"] for f in json.load(open(os.path.expanduser("~/Desktop/cuyahoga_transfers_raw.json")))["features"]]
print(f"raw records: {len(raw):,}")

def to_year(s):
    if s is None: return None
    if isinstance(s, (int, float)):
        # millisecond epoch
        try: return int(s / 1000 / 86400 / 365.25 + 1970)
        except: return None
    # ISO date string
    try: return int(s[:4]) if len(s) >= 4 and s[:4].isdigit() else None
    except: return None

BUCKETS = [
    ("pre-2008", lambda y: y is not None and y < 2008),
    ("2008-2012", lambda y: y is not None and 2008 <= y <= 2012),
    ("2013-2016", lambda y: y is not None and 2013 <= y <= 2016),
    ("2017-2020", lambda y: y is not None and 2017 <= y <= 2020),
    ("2021-2026", lambda y: y is not None and 2021 <= y <= 2026),
]

def bucket(y):
    if y is None: return "unknown"
    for name, pred in BUCKETS:
        if pred(y): return name
    return "unknown"

pair_buckets = defaultdict(set)

for r in raw:
    g = _u(r.get("grantor"))
    t = _u(r.get("grantee"))
    if not g or not t or g == t: continue
    y = to_year(r.get("last_transfer_date"))
    b = bucket(y)
    u, v = f"owner|{g}", f"owner|{t}"
    pair_buckets[(u, v)].add(b)

print(f"distinct pairs: {len(pair_buckets):,}")
multi = sum(1 for s in pair_buckets.values() if len(s) > 1)
print(f"pairs in 2+ buckets: {multi:,} ({100*multi/max(1,len(pair_buckets)):.1f}%)")

T = nx.DiGraph()
for (u, v), buckets in pair_buckets.items():
    for b in buckets:
        if T.has_edge(u, v):
            T[u][v]["weight"] = T[u][v].get("weight", 0) + 1
        else:
            T.add_edge(u, v, relation="transacted", bucket=b, weight=1)

pickle.dump(T, open(os.path.expanduser("~/Desktop/cuyahoga_transfers_timesliced.pkl"), "wb"))
print(f"\nwrote cuyahoga_transfers_timesliced.pkl: {T.number_of_nodes():,} nodes, {T.number_of_edges():,} edges")

bc = defaultdict(int)
for u, v, d in T.edges(data=True): bc[d["bucket"]] += 1
for b, c in sorted(bc.items(), key=lambda x: -x[1]):
    print(f"  {b:12s} {c:7,}")
