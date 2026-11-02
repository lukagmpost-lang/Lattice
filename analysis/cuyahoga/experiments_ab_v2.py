import os, pickle, re
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
T = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_transfers.pkl"), "rb"))
LB = "LAND REUTILIZATION"

print("=" * 70)
print("EXPERIMENT A: THREE BLACK KNIGHTS vs ORLEAN")
print("=" * 70)

# Restrict to company variants only
def tbk_ok(s):
    n = _u(s)
    return "THREE BLACK KNIGHTS" in n

def orl_ok(s):
    n = _u(s)
    if "DORLEAN" in n or "ORLEANS" in n: return False
    return n.startswith("THE ORLEAN") or n.startswith("ORLEAN CO") or \
           n.startswith("ORLEAN DEV") or n == "ORLEAN COMPANY" or \
           n.startswith("ORLEAN 23925") or n.startswith("ORLEAN WT")

tbk = [n for n in T.nodes if n.startswith("owner|") and tbk_ok(n[6:])]
orl = [n for n in T.nodes if n.startswith("owner|") and orl_ok(n[6:])]

print(f"\nTBK variants: {tbk}")
print(f"Orlean variants: {orl}")

if not tbk or not orl:
    print("Missing one side"); raise SystemExit(1)

tbk_g, orl_g = set(), set()
tbk_gt, orl_gt = set(), set()
for n in tbk:
    tbk_g |= set(T.predecessors(n))
    tbk_gt |= set(T.successors(n))
for n in orl:
    orl_g |= set(T.predecessors(n))
    orl_gt |= set(T.successors(n))

print(f"\nTBK: {len(tbk_g)} grantors, {len(tbk_gt)} grantees")
print(f"Orlean: {len(orl_g)} grantors, {len(orl_gt)} grantees")

sg = tbk_g & orl_g
sgt = tbk_gt & orl_gt
print(f"\nShared grantors: {len(sg)}")
for s in sg: print(f"  {s[6:][:70]}")
print(f"\nShared grantees: {len(sgt)}")
for s in sgt: print(f"  {s[6:][:70]}")

# Top grantors for each (which banks / individuals / entities feed them)
print("\nTBK top grantors (by parcel count):")
tbk_gc = Counter()
for n in tbk:
    for g in T.predecessors(n):
        tbk_gc[g] += T[g][n].get("weight",1)
for g, c in tbk_gc.most_common(10):
    print(f"  {c:3d}  {g[6:][:65]}")

print("\nOrlean top grantors (by parcel count):")
orl_gc = Counter()
for n in orl:
    for g in T.predecessors(n):
        orl_gc[g] += T[g][n].get("weight",1)
for g, c in orl_gc.most_common(10):
    print(f"  {c:3d}  {g[6:][:65]}")

# Shared mailing addresses (guard missing nodes)
print("\nShared mailing addresses:")
tbk_a, orl_a = set(), set()
for n in tbk:
    if n not in G: continue
    for nb in G.neighbors(n):
        if G.nodes[nb].get("type") == "address": tbk_a.add(nb)
for n in orl:
    if n not in G: continue
    for nb in G.neighbors(n):
        if G.nodes[nb].get("type") == "address": orl_a.add(nb)
sa = tbk_a & orl_a
print(f"  {len(sa)} shared")
for a in sa:
    print(f"  {G.nodes[a].get('street')}, {G.nodes[a].get('zip')}")
print(f"\nTBK addresses ({len(tbk_a)}):")
for a in list(tbk_a)[:5]:
    print(f"  {G.nodes[a].get('street')}, {G.nodes[a].get('zip')}")
print(f"Orlean addresses ({len(orl_a)}):")
for a in list(orl_a)[:5]:
    print(f"  {G.nodes[a].get('street')}, {G.nodes[a].get('zip')}")

# Acquisition timing overlap
print("\nAcquisition date ranges:")
for label, nodes in [("TBK", tbk), ("Orlean", orl)]:
    dates = []
    for n in nodes:
        for u in T.predecessors(n):
            d = T[u][n].get("first_date")
            if d: dates.append(d)
    if dates:
        print(f"  {label}: {min(dates)} to {max(dates)}, {len(dates)} acquisitions")

# Direct land-bank origin
print("\nDirect from land bank?")
print(f"  TBK: {any(LB in _u(u) for n in tbk for u in T.predecessors(n))}")
print(f"  Orlean: {any(LB in _u(u) for n in orl for u in T.predecessors(n))}")

print("\n" + "=" * 70)
print("EXPERIMENT B: DISPOSITION FOLLOW-THROUGH")
print("=" * 70)

NP = ("CHN HOUSING","HABITAT","SLAVIC VILLAGE","DETROIT SHOREWAY","FAMICOS",
      "LARCHMERE","LA VILLA","SWDS HOMES","NSP HOMES","CLEVELAND GREEN",
      "CHURCH","HOSPITAL","UNIVERSITY","FOUNDATION","CONSERVANCY","CDC")
GOV = ("CITY OF","COUNTY","STATE OF","UNITED STATES","HUD","SECRETARY OF",
       "BOARD OF","DISTRICT","AUTHORITY","VILLAGE OF")

def cat(name):
    n = _u(name)
    if any(k in n for k in GOV): return "government"
    if any(k in n for k in NP): return "nonprofit"
    if "," in n and not any(k in n for k in ["LLC","CORP","INC","LTD","LP"]): return "person"
    if any(k in n for k in ["LLC","CORP","INC","LTD","LP","L.P"]): return "entity"
    return "unknown"

rec_from_lb = {}
for u, v, d in T.edges(data=True):
    if LB in _u(u):
        rec_from_lb.setdefault(v, []).append(d.get("weight",1))

held, resold, n_held, n_resold = Counter(), Counter(), Counter(), Counter()
for rec in rec_from_lb:
    if rec not in T: continue
    c = cat(rec[6:] if rec.startswith("owner|") else rec)
    outs = [(t, T[rec][t].get("weight",1)) for t in T.successors(rec) if LB not in _u(t)]
    if outs:
        resold[c] += sum(w for _, w in outs); n_resold[c] += 1
    else:
        held[c] += sum(rec_from_lb[rec]); n_held[c] += 1

print(f"\n{'category':12s} {'held':>8s} {'n_held':>8s} {'resold':>8s} {'n_resold':>10s}")
for c in ("government","nonprofit","person","entity","unknown"):
    print(f"  {c:12s} {held.get(c,0):>8d} {n_held.get(c,0):>8d} "
          f"{resold.get(c,0):>8d} {n_resold.get(c,0):>10d}")

print("\nCHN HOUSING follow-through:")
for n in T.nodes:
    if "CHN HOUSING" in _u(n) or "CNN HOUSING" in _u(n):
        ins = [(T[s][n].get("weight",1), s[6:][:40]) for s in T.predecessors(n)]
        outs = [(T[n][t].get("weight",1), t[6:][:40]) for t in T.successors(n)]
        print(f"  {n[6:]}")
        print(f"    in:  {sum(w for w,_ in ins)} parcels / {len(ins)} sources")
        print(f"    out: {sum(w for w,_ in outs)} parcels / {len(outs)} targets")
        for w, name in outs[:5]:
            print(f"      -> {w:3d} {name}")

print("\nHABITAT follow-through:")
for n in T.nodes:
    if "HABITAT" in _u(n):
        ins = sum(T[s][n].get("weight",1) for s in T.predecessors(n))
        outs = [(T[n][t].get("weight",1), t[6:][:40]) for t in T.successors(n)]
        print(f"  {n[6:][:60]}: in={ins} out={sum(w for w,_ in outs)}")
        for w, name in outs[:3]:
            print(f"    -> {w:3d} {name}")
