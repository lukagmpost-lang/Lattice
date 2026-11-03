import json, os, re, pickle
from datetime import datetime, timezone
import networkx as nx

rows = [f["attributes"] for f in json.load(open(os.path.expanduser("~/Desktop/cuyahoga_transfers_raw.json")))["features"]]
print(f"loaded {len(rows):,} rows")

CAP = {"TRUSTEE","SUCCESSOR TRUSTEE","SUCC TRS","TRS","PRESIDENT","VICE PRESIDENT","VP",
       "SECRETARY","TREASURER","MANAGING MEMBER","MEMBER","MANAGER","GENERAL PARTNER","GP",
       "REGISTERED AGENT","ATTORNEY","ATTY","ESQ","ESQUIRE","ATTORNEY IN FACT","AIF",
       "ET AL","ET UX","ET VIR"}
ENT_RE = re.compile(r"^(?:AN? |THE |FORMERLY )[A-Z ]*(?:LLC|L\.L\.C|CORP|CORPORATION|INC|INCORPORATED|LP|L\.P|LLP|L\.L\.P|LTD|LIMITED|COMPANY|CO|TRUST|PARTNERSHIP|ASSOCIATION|ASSN)\b.*$")
PLACE = {"SEE PARCEL","NONE","UNKNOWN","NULL","N/A","","TBD"}

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()
def _n(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip()
def strip_cap(name):
    n = _u(name)
    if not n: return ""
    changed = True
    while changed:
        changed = False
        if "," in n:
            h, t = n.rsplit(",", 1)
            ts = t.strip()
            if ts in CAP or ENT_RE.match(ts):
                n = h.strip(); changed = True; continue
        for sfx in (" ET AL"," ET UX"," ET VIR"):
            if n.endswith(sfx):
                n = n[:-len(sfx)].strip(); changed = True; break
    return n
def split_parties(name):
    n = _u(name)
    if not n or n in PLACE or n.startswith("SEE PARCEL"): return []
    out = []
    for p in re.split(r"\s+(?:&|AND)\s+", n):
        p = strip_cap(p)
        if p and len(p) >= 3 and p not in PLACE: out.append(p)
    return list(dict.fromkeys(out))
def dt(ms):
    try: return datetime.fromtimestamp(int(ms)/1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except: return None
def fl(v):
    try: return float(v) if v is not None else None
    except: return None

print("building transfer graph...")
G = nx.DiGraph()
amp_ex = []
for r in rows:
    gs = split_parties(r.get("grantor"))
    ts = split_parties(r.get("grantee"))
    if not gs or not ts: continue
    d, a = dt(r.get("last_transfer_date")), fl(r.get("last_sales_amount"))
    bp = _n(r.get("book_page")) or None
    if "&" in _u(r.get("grantor","")) and len(amp_ex) < 8 and len(gs) > 1:
        amp_ex.append((r["grantor"], gs))
    for g in gs:
        for t in ts:
            if g == t: continue
            gk, tk = f"owner|{g}", f"owner|{t}"
            if G.has_edge(gk, tk):
                e = G[gk][tk]; e["weight"] += 1
                if a: e["total_amount"] += a
                if d:
                    if not e.get("first_date") or d < e["first_date"]: e["first_date"] = d
                    if not e.get("last_date")  or d > e["last_date"]:  e["last_date"]  = d
                if bp: e["book_pages"].append(bp)
            else:
                G.add_edge(gk, tk, weight=1, total_amount=a or 0.0,
                           first_date=d, last_date=d,
                           book_pages=[bp] if bp else [], relation="transfer")

with open(os.path.expanduser("~/Desktop/cuyahoga_transfers.pkl"), "wb") as fh:
    pickle.dump(G, fh)
print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

print("\nloading existing ownership pickle for overlap...")
existing = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_graph.pkl"), "rb"))
existing_owners = {n[6:] for n in existing.nodes if n.startswith("owner|")}

grantors = set(u for u,_ in G.out_degree)
grantees = set(v for _,v in G.in_degree)
all_nodes = grantors | grantees
transfer_names = {n[6:] for n in all_nodes}
overlap = transfer_names & existing_owners

print("\n" + "="*72)
print("1. NODE COUNT & OVERLAP")
print(f"   grantors:                     {len(grantors):,}")
print(f"   grantees:                     {len(grantees):,}")
print(f"   total transfer nodes:         {len(all_nodes):,}")
print(f"   overlap with existing owners: {len(overlap):,} ({100*len(overlap)/max(1,len(transfer_names)):.1f}%)")

print("\n2. & SPLIT PROOF")
for i,(raw,parts) in enumerate(amp_ex[:5], 1):
    print(f"   [{i}] RAW: {raw[:80]}")
    for p in parts: print(f"        -> owner|{p}")

ws = [d["weight"] for _,_,d in G.edges(data=True)]
nm = sum(1 for w in ws if w > 1)
print("\n3. EDGE WEIGHT DISTRIBUTION")
print(f"   edges:       {len(ws):,}")
print(f"   weight ==1:  {len(ws)-nm:,} ({100*(len(ws)-nm)/max(1,len(ws)):.1f}%)")
print(f"   weight >1:   {nm:,} ({100*nm/max(1,len(ws)):.1f}%)")
if ws:
    print(f"   max weight:  {max(ws):,}")
    print(f"   mean weight: {sum(ws)/len(ws):.2f}")

print("\n4. TOP 10 GRANTORS  (sold to N distinct buyers)")
for n,d in sorted(G.out_degree, key=lambda x:-x[1])[:10]:
    p = sum(G[n][t]["weight"] for t in G.successors(n))
    print(f"   {d:5d} buyers, {p:6d} parcels  {n[6:][:70]}")

print("\nTOP 10 GRANTEES  (bought from N distinct sellers)")
for n,d in sorted(G.in_degree, key=lambda x:-x[1])[:10]:
    p = sum(G[s][n]["weight"] for s in G.predecessors(n))
    print(f"   {d:5d} sellers, {p:6d} parcels  {n[6:][:70]}")
