import json, os, pickle, re
from collections import Counter, defaultdict
_u = lambda s: re.sub(r"\s+"," ",str(s)).strip().upper() if s else ""
G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"),"rb"))
raw = [f["attributes"] for f in json.load(open(os.path.expanduser("~/Desktop/cuyahoga_transfers_raw.json")))["features"]]
print("raw records:", len(raw))
LB_KW = ("LAND REUTILIZATION","LAND REUTILZATION","LAND REUTLIZATION","LAND RETULIZATION","LAND TEUTILIZATION","CCLRC","CITY OF CLEVELAND L/B","CLEVELAND CITY OF LB")
def is_lb(n):
    u=_u(n); return any(k in u for k in LB_KW)
parcels = defaultdict(list)
for r in raw:
    pid = r.get("parcel_id")
    if not pid: continue
    parcels[str(pid)].append(r)
last = {}
for pid, rs in parcels.items():
    rs.sort(key=lambda r: float(r.get("last_transfer_date") or 0))
    last[pid] = rs[-1]
print("distinct parcels:", len(last))
cats = Counter()
for r in last.values():
    cats[(is_lb(r.get("grantor")), is_lb(r.get("grantee")))] += 1
still = cats[(False,True)] + cats[(True,True)]
left  = cats[(True,False)]
never = cats[(False,False)]
print(f"\nstill in LB:  {still:,}")
print(f"  of which intra-LB last: {cats[(True,True)]:,}")
print(f"  of which ext receipt:   {cats[(False,True)]:,}")
print(f"left LB:      {left:,}")
print(f"never in LB:  {never:,}")
print(f"\nHold rate:     {100*still/max(1,still+left):.1f}%")
print(f"Release rate:  {100*left/max(1,still+left):.1f}%")
