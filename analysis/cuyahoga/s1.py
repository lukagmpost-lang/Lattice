import os, pickle, re
_u = lambda s: re.sub(r"\s+"," ",str(s)).strip().upper() if s else ""
G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"),"rb"))
is_lb = lambda n: any(s in _u(n) for s in ("REUTIL","LAND BANK","LRP","LRC"))
lb = [(n, G.nodes[n].get("total_parcels",0)) for n in G.nodes if is_lb(n)]
lb.sort(key=lambda x:-x[1])
print("LB nodes in G:", len(lb))
print("Top 20:")
for n,c in lb[:20]: print(f"  {c:5d}  {n[6:][:70]}")
print("ALL LB SUM:", sum(c for _,c in lb))
def is_cle(n):
    u=_u(n); return "CLEVELAND" in u and "EAST" not in u and any(k in u for k in ("LRP","LAND REUTIL","LAND BANK"))
def is_ecl(n):
    u=_u(n); return "EAST CLEVELAND" in u and is_lb(n)
def is_cuy(n):
    u=_u(n); return "CCLRC" in u or ("CUYAHOGA" in u and any(k in u for k in ("LRC","LAND REUTIL","LAND BANK")))
tot = lambda ns: sum(G.nodes[n].get("total_parcels",0) for n in ns)
cle={n for n,_ in lb if is_cle(n)}; ecl={n for n,_ in lb if is_ecl(n)}; cuy={n for n,_ in lb if is_cuy(n)}
maj = cle|ecl|cuy
print(f"\nCity of Cleveland LRP: {len(cle)} nodes {tot(cle):,} parcels")
print(f"East Cleveland LB:     {len(ecl)} nodes {tot(ecl):,} parcels")
print(f"Cuyahoga County LRC:   {len(cuy)} nodes {tot(cuy):,} parcels")
print(f"MAJORS:                {len(maj)} nodes {tot(maj):,} parcels")
print(f"ALL LB:                {len(lb)} nodes {tot(lb):,} parcels")
print(f"Other LB:              {len(lb)-len(maj)} nodes {tot(lb)-tot(maj):,} parcels")
