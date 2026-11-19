import json, os, pickle, re
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
raw = [f["attributes"] for f in json.load(open(os.path.expanduser("~/Desktop/cuyahoga_transfers_raw.json")))["features"]]
print(f"raw records: {len(raw):,}")

LB_KW = ("LAND REUTILIZATION","LAND REUTILZATION","LAND REUTLIZATION",
         "LAND RETULIZATION","LAND TEUTILIZATION","L/B","CITY OF LB","CLEVELAND CITY OF LB")
def is_lb(name):
    n = _u(name)
    return any(k in n for k in LB_KW)

cats = Counter()
for r in raw:
    g = is_lb(r.get("grantor")); t = is_lb(r.get("grantee"))
    cats[(g,t)] += 1

print("\n=== PARCEL CLASSIFICATION (last transfer) ===")
print(f"  LB -> LB (self):      {cats[(True,True)]:>6,}")
print(f"  LB -> non-LB (out):   {cats[(True,False)]:>6,}")
print(f"  non-LB -> LB (in):    {cats[(False,True)]:>6,}")
print(f"  non-LB -> non-LB:     {cats[(False,False)]:>6,}")

held = cats[(False,True)] + cats[(True,True)]
released = cats[(True,False)]
print(f"\n  held (last transfer into LB): {held:,}")
print(f"  released (last transfer out): {released:,}")
print(f"  hold rate:                    {100*held/max(1,held+released):.1f}%")
print(f"  external release rate:        {100*released/max(1,held+released):.1f}%")

print("\n=== CURRENT LB HOLDINGS (from G) ===")
lb_parcels = 0
for o, d in G.nodes(data=True):
    if o.startswith("owner|") and is_lb(o[6:]):
        lb_parcels += sum(1 for p in G.neighbors(o) if G.nodes[p].get("type")=="parcel")
print(f"  {lb_parcels:,} parcels currently owned by LB variants")

print("\n=== COUNTY DIAGNOSTIC ===")
def is_county(name):
    n = _u(name)
    return "CUYAHOGA" in n and "LAND" in n and ("REUTIL" in n or "RETUL" in n or "REUTL" in n or "CCLRC" in n or "CORP" in n)
county_G = sum(1 for o in G.nodes if o.startswith("owner|") and is_county(o[6:])
               for p in G.neighbors(o) if G.nodes[p].get("type")=="parcel")
county_in = sum(1 for r in raw if is_county(r.get("grantee")))
county_out = sum(1 for r in raw if is_county(r.get("grantor")))
print(f"  county owned (G):     {county_G:,}")
print(f"  county grantee (raw): {county_in:,}")
print(f"  county grantor (raw): {county_out:,}")
print(f"  net vs raw-grantee:   {county_G - county_in:+,}")

print("\n=== PRIVATE SCATTERED-SITE THRESHOLD SWEEP ===")
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

for thresh in (3, 5, 10, 20):
    total = 0; owners = 0
    for o, d in G.nodes(data=True):
        if not o.startswith("owner|"): continue
        if not is_private(o[6:]): continue
        ps = [p for p in G.neighbors(o) if G.nodes[p].get("type")=="parcel"]
        if len(ps) >= thresh:
            total += len(ps); owners += 1
    ratio = lb_parcels / max(1, total)
    print(f"  {thresh:2d}+ parcels: {owners:>5,} owners / {total:>6,} parcels | ratio {ratio:.1f}:1")
