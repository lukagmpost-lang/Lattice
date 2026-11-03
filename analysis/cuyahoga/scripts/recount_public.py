import os, pickle, re
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

# With v6, everything is tagged. Count parcels by owner kind.
kind_parcels = Counter()
kind_owners = Counter()
for n, d in G.nodes(data=True):
    if not n.startswith("owner|"): continue
    kind = d.get("kind", "unknown")
    kind_owners[kind] += 1
    ps = [p for p in G.neighbors(n) if G.nodes[p].get("type") == "parcel"]
    kind_parcels[kind] += len(ps)

print("=== PARCELS BY OWNER KIND (v6) ===")
for k in ("person","entity","trust","government","placeholder","unknown"):
    print(f"  {k:12s} {kind_owners[k]:>6,} owners / {kind_parcels[k]:>7,} parcels")

# Now specifically the land bank
LB_KW = ("LAND REUTILIZATION","LAND REUTILZATION","LAND REUTLIZATION",
         "LAND RETULIZATION","LAND TEUTILIZATION","L/B")
def is_lb(name): return any(k in _u(name) for k in LB_KW)

lb_parcels = set()
for n, d in G.nodes(data=True):
    if n.startswith("owner|") and is_lb(n[6:]):
        for p in G.neighbors(n):
            if G.nodes[p].get("type") == "parcel":
                lb_parcels.add(p)

print(f"\n=== LAND BANK (v6) ===")
print(f"  unique parcels: {len(lb_parcels):,}")

# Now the threshold sweep with v6 categories
private_parcels_by_threshold = {}
for thresh in (3, 5, 10, 20):
    owner_set = []
    for n, d in G.nodes(data=True):
        if not n.startswith("owner|"): continue
        if d.get("kind") not in ("person","entity","trust"):
            continue
        ps = [p for p in G.neighbors(n) if G.nodes[p].get("type") == "parcel"]
        if len(ps) >= thresh:
            owner_set.append((n, ps))
    unique_p = set()
    for _, ps in owner_set:
        unique_p.update(ps)
    private_parcels_by_threshold[thresh] = (len(owner_set), len(unique_p))

print("\n=== PRIVATE THRESHOLD SWEEP (v6, government excluded) ===")
for thresh, (owners, parcels) in private_parcels_by_threshold.items():
    ratio = len(lb_parcels) / max(1, parcels)
    print(f"  {thresh:2d}+ parcels: {owners:>5,} owners / {parcels:>7,} parcels | LB/private ratio: {ratio:.2f}")

# Top persons with v6
persons = []
for n, d in G.nodes(data=True):
    if d.get("kind") in ("person","trust") and n.startswith("owner|"):
        ps = [p for p in G.neighbors(n) if G.nodes[p].get("type") == "parcel"]
        if ps: persons.append((n, len(ps), d["kind"]))
persons.sort(key=lambda x: -x[1])
print("\n=== TOP 15 PERSONS (v6) ===")
for n, c, k in persons[:15]:
    print(f"  {c:4d}  [{k:6s}]  {n[6:][:60]}")
