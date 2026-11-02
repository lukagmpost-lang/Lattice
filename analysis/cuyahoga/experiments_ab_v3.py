import os, pickle, re
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
T = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_transfers.pkl"), "rb"))

LB_SUBSTR = ("REUTIL", "LAND BANK", "LRP", "LRC")
def is_lb(name):
    u = _u(name)
    return any(s in u for s in LB_SUBSTR)

lb_nodes = sorted({n for n in T.nodes if is_lb(n)})
print("=" * 70)
print("DIAGNOSTIC")
print("=" * 70)
print(f"LB nodes matched: {len(lb_nodes)}")
for n in lb_nodes[:15]: print(f"  {n[:100]!r}")
print(f"\nT node prefixes: {sorted(set(n.split('|')[0] for n in list(T.nodes)[:5000]))}")
print(f"G node prefixes: {sorted(set(n.split('|')[0] for n in list(G.nodes)[:5000]))}")
overlap = set(T.nodes) & set(G.nodes)
print(f"T nodes: {len(set(T.nodes)):,}  G nodes: {len(set(G.nodes)):,}  overlap: {len(overlap):,}")
tk = set()
for u,v,d in T.edges(data=True): tk |= set(d.keys())
print(f"T edge attrs: {sorted(tk)}")

print("\n" + "=" * 70)
print("EXPERIMENT A: THREE BLACK KNIGHTS vs ORLEAN")
print("=" * 70)

def find_nodes(substr): return [n for n in T.nodes if substr in _u(n)]
tbk = find_nodes("THREE BLACK KNIGHTS"); orl = find_nodes("ORLEAN")
print(f"TBK nodes: {tbk}")
print(f"Orlean nodes: {orl}")

if not tbk or not orl:
    print("!! One or both not found in T. Skipping A.")
else:
    tbk_g = set(); tbk_gt = set(); orl_g = set(); orl_gt = set()
    for n in tbk:
        tbk_g |= set(T.predecessors(n)); tbk_gt |= set(T.successors(n))
    for n in orl:
        orl_g |= set(T.predecessors(n)); orl_gt |= set(T.successors(n))
    print(f"TBK: {len(tbk_g)} grantors, {len(tbk_gt)} grantees")
    print(f"Orlean: {len(orl_g)} grantors, {len(orl_gt)} grantees")
    sg = tbk_g & orl_g; sgt = tbk_gt & orl_gt
    print(f"Shared grantors: {len(sg)}")
    for s in list(sg)[:15]: print(f"  {s[6:][:65]}")
    print(f"Shared grantees: {len(sgt)}")
    for s in list(sgt)[:15]: print(f"  {s[6:][:65]}")
    tbk_a = set(); orl_a = set()
    for n in tbk:
        if n not in G: continue
        for nb in G.neighbors(n):
            if G.nodes[nb].get("type") == "address": tbk_a.add(nb)
    for n in orl:
        if n not in G: continue
        for nb in G.neighbors(n):
            if G.nodes[nb].get("type") == "address": orl_a.add(nb)
    sa = tbk_a & orl_a
    print(f"Shared mailing addresses: {len(sa)}")
    for a in sa: print(f"  {G.nodes[a].get('street')}, {G.nodes[a].get('zip')}")
    print("Direct LB acquisition:")
    print(f"  TBK: {any(is_lb(u) for n in tbk for u in T.predecessors(n))}")
    print(f"  Orlean: {any(is_lb(u) for n in orl for u in T.predecessors(n))}")

print("\n" + "=" * 70)
print("EXPERIMENT B: DISPOSITION FOLLOW-THROUGH")
print("=" * 70)

NP = ("CHN HOUSING","HABITAT","SLAVIC VILLAGE","DETROIT SHOREWAY","FAMICOS",
      "LARCHMERE","LA VILLA","SWDS HOMES","NSP HOMES","CLEVELAND GREEN",
      "CHURCH","HOSPITAL","UNIVERSITY","FOUNDATION","CONSERVANCY","CDC")
GOV = ("CITY OF","COUNTY","STATE OF","UNITED STATES","HUD","SECRETARY OF",
       "BOARD OF","DISTRICT","AUTHORITY","VILLAGE OF")

def cat_recipient(name):
    n = _u(name)
    if any(k in n for k in GOV): return "government"
    if any(k in n for k in NP): return "nonprofit"
    if "," in n and not any(k in n for k in ["LLC","CORP","INC","LTD","LP"]): return "person"
    if any(k in n for k in ["LLC","CORP","INC","LTD","LP","L.P"]): return "entity"
    return "unknown"

recipients_from_lb = {}
for u, v, d in T.edges(data=True):
    if is_lb(u): recipients_from_lb.setdefault(v, []).append(d.get("weight",1))
print(f"\n{len(recipients_from_lb)} distinct LB recipients")

held = Counter(); resold_n = Counter(); resold_wt = Counter()
for rec in recipients_from_lb:
    if rec not in T: continue
    cat = cat_recipient(rec[6:] if rec.startswith("owner|") else rec)
    outs = [(t, T[rec][t].get("weight",1)) for t in T.successors(rec) if not is_lb(t)]
    n_in = sum(recipients_from_lb[rec])
    if outs:
        resold_n[cat] += 1
        resold_wt[cat] += sum(w for _,w in outs)
    else:
        held[cat] += n_in

print(f"\n{'category':15s} {'held_parcels':>14s} {'resold_recips':>15s} {'outbound_wt':>13s}")
for cat in ("government","nonprofit","person","entity","unknown"):
    print(f"  {cat:15s} {held.get(cat,0):14d} {resold_n.get(cat,0):15d} {resold_wt.get(cat,0):13d}")
print("\nNOTE: 'held_parcels' = LB-origin parcels recipient still holds.")
print("      'resold_recips' = recipients with any non-LB outbound edge.")
print("      'outbound_wt' = all non-LB outbound weight, NOT parcel-matched to LB receipts.")

print("\nCHN HOUSING follow-through:")
for n in T.nodes:
    if "CHN HOUSING" in _u(n) or "CNN HOUSING" in _u(n):
        ins = [(T[s][n].get("weight",1), s[6:][:40]) for s in T.predecessors(n)]
        outs = [(T[n][t].get("weight",1), t[6:][:40]) for t in T.successors(n)]
        print(f"  {n[6:]}")
        print(f"    LB-received: {sum(recipients_from_lb.get(n, [0]))} parcels")
        print(f"    total in: {sum(w for w,_ in ins)} from {len(ins)} sources")
        print(f"    total out: {sum(w for w,_ in outs)} to {len(outs)} targets")
        for w, name in outs[:5]:
            print(f"      -> {w:3d} to {name}")
