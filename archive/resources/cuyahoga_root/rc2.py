import os, pickle, re
_u = lambda s: re.sub(r"\s+"," ",str(s)).strip().upper() if s else ""
G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"),"rb"))
LB_KW = ("LAND REUTILIZATION","LAND REUTILZATION","LAND REUTLIZATION","LAND RETULIZATION","LAND TEUTILIZATION","CCLRC")
def is_lb(n): return any(k in _u(n) for k in LB_KW)
lb_total = sum(1 for o,d in G.nodes(data=True) if o.startswith("owner|") and is_lb(o[6:])
               for p in G.neighbors(o) if G.nodes[p].get("type")=="parcel")
print("LB current parcels:", lb_total)
GOV_PREFIX = ("CITY OF ","VILLAGE OF ","STATE OF ","COUNTY OF ","TOWNSHIP OF ","BOARD OF ","UNITED STATES ","SECRETARY OF ","DEPARTMENT OF ","DISTRICT OF ")
NP_KW = ("FOUNDATION","CONSERVANCY","UNIVERSITY","COLLEGE","HOSPITAL","CLINIC","CHURCH","DIOCESE","HABITAT","HOUSING PARTNERS","CDC","COMMUNITY DEVELOPMENT")
def is_gov(n):
    u=_u(n)
    if any(u.startswith(p) for p in GOV_PREFIX): return True
    if re.search(r"\sCOUNTY(\s|$)", u): return True
    if "HOUSING AUTHORITY" in u: return True
    return False
def is_private(n):
    u=_u(n)
    return not (is_gov(u) or is_lb(u) or any(k in u for k in NP_KW))
print(f"\n{'filter':28s} {'owners':>8s} {'parcels':>9s} {'ratio':>8s}")
for th in (2,3,5,10):
    for zm in (0,2):
        owners=0; total=0
        for o,d in G.nodes(data=True):
            if not o.startswith("owner|"): continue
            if d.get("kind") not in ("person","entity","trust","unknown"): continue
            if not is_private(o[6:]): continue
            if d.get("total_parcels",0)<th or d.get("n_zips",0)<zm: continue
            owners+=1; total+=d["total_parcels"]
        print(f"  >= {th}p, zips>={zm}{'':10s} {owners:8d} {total:9,d} {lb_total/max(1,total):7.1f}:1")
