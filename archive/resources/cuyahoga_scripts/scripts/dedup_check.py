import os, pickle, re
from collections import Counter, defaultdict

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

# How many owners does each parcel have?
parcel_owners = defaultdict(list)
for n, d in G.nodes(data=True):
    if d.get("type") != "parcel": continue
    for o in G.neighbors(n):
        if o.startswith("owner|"):
            parcel_owners[n].append(o)

dist = Counter(len(v) for v in parcel_owners.values())
print("=== OWNERS PER PARCEL ===")
for k in sorted(dist):
    print(f"  {k} owners: {dist[k]:>8,} parcels")

total_owners = sum(len(v) for v in parcel_owners.values())
print(f"\n  total owner->parcel edges: {total_owners:,}")
print(f"  unique parcels: {len(parcel_owners):,}")
print(f"  avg owners per parcel: {total_owners/max(1,len(parcel_owners)):.2f}")

# Double-counting: sum of per-owner parcel counts vs unique parcels
per_owner = Counter()
for p, owners in parcel_owners.items():
    for o in owners:
        per_owner[o] += 1
total_per_owner = sum(per_owner.values())
print(f"\n  sum of per-owner counts: {total_per_owner:,}")
print(f"  unique parcels counted once: {len(parcel_owners):,}")
print(f"  overcount factor: {total_per_owner/max(1,len(parcel_owners)):.3f}")
print(f"  parcels held by >1 owner: {sum(1 for v in parcel_owners.values() if len(v) > 1):,}")

# Do the same for the land bank
LB_KW = ("LAND REUTILIZATION","LAND REUTILZATION","LAND REUTLIZATION",
         "LAND RETULIZATION","LAND TEUTILIZATION","L/B")
def is_lb(n): return any(k in _u(n) for k in LB_KW)

lb_parcels = set()
for p, owners in parcel_owners.items():
    if any(is_lb(o[6:]) for o in owners):
        lb_parcels.add(p)

print(f"\n=== LAND BANK UNIQUE PARCELS ===")
print(f"  unique parcels with any LB owner: {len(lb_parcels):,}")

# Threshold sweep using UNIQUE parcels
GOV = ("CITY OF","COUNTY","STATE OF","UNITED STATES","U S A","BOARD OF",
       "DISTRICT","AUTHORITY","VILLAGE OF","SECRETARY OF","DEPARTMENT OF")
NP = ("FOUNDATION","CONSERVANCY","UNIVERSITY","COLLEGE","HOSPITAL","CLINIC",
      "CHURCH","DIOCESE","HABITAT","HOUSING PARTNERS","CDC","COMMUNITY DEVELOPMENT")

def is_private(name):
    n = _u(name)
    if is_lb(n): return False
    if any(k in n for k in GOV): return False
    if any(k in n for k in NP): return False
    return True

print(f"\n=== THRESHOLD SWEEP (unique parcels, no double count) ===")
for thresh in (3, 5, 10, 20):
    owners_at = [o for o, c in per_owner.items()
                 if c >= thresh and is_private(o[6:])]
    unique_p = set()
    for o in owners_at:
        for p in G.neighbors(o):
            if G.nodes[p].get("type") == "parcel":
                unique_p.add(p)
    print(f"  {thresh:2d}+ parcels: {len(owners_at):>5,} owners hold {len(unique_p):>6,} UNIQUE parcels")

# With double-counting (old method)
print(f"\n=== OLD METHOD (sum of per-owner, may double count) ===")
for thresh in (3, 5, 10, 20):
    total = 0; owners_at = 0
    for o, c in per_owner.items():
        if c >= thresh and is_private(o[6:]):
            total += c; owners_at += 1
    print(f"  {thresh:2d}+ parcels: {owners_at:>5,} owners hold {total:>6,} parcels (may overcount)")
