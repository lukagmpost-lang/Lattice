import os, pickle, re
from collections import Counter, defaultdict
import networkx as nx

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

print("loading pickles...")
G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_graph.pkl"), "rb"))
T = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_transfers.pkl"), "rb"))
print(f"  ownership: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
print(f"  transfers: {T.number_of_nodes():,} nodes, {T.number_of_edges():,} edges")

ENTITY_KEYWORDS = ("LLC","L.L.C","CORP","INC","INCORPORATED","LP","LLP","LTD",
                   "LIMITED","COMPANY","TRUST","TRS","ASSN","ASSOC","PARTNERSHIP",
                   "HOLDINGS","PROPERTIES","REALTY","DEVELOPMENT","FUND","GROUP",
                   "BANK","CREDIT","CHURCH","DIOCESE","BISHOP","HOSPITAL",
                   "UNIVERSITY","COLLEGE","FOUNDATION","SCHOOL","DISTRICT",
                   "AUTHORITY","COUNTY","CITY OF","STATE OF","UNITED STATES")

def classify(name):
    n = _u(name)
    if any(k in n for k in ENTITY_KEYWORDS): return "entity"
    if "," in n:
        head = n.split(",",1)[0].strip()
        if head and re.match(r"^[A-Z][A-Z .'-]+$", head) and len(head.split()) <= 3:
            return "person"
    return "unknown"

def situs_zip(s):
    if not s: return ""
    parts = s.rsplit(",", 1)
    return parts[-1].strip() if len(parts) == 2 else ""

def val(p):
    try: return float(G.nodes[p].get("value") or 0)
    except (TypeError, ValueError): return 0.0

print("\nclassifying owners...")
cls = {n: classify(n[6:]) for n in G.nodes if n.startswith("owner|")}
print(f"  person:  {sum(1 for c in cls.values() if c=='person'):,}")
print(f"  entity:  {sum(1 for c in cls.values() if c=='entity'):,}")
print(f"  unknown: {sum(1 for c in cls.values() if c=='unknown'):,}")

print("\nadding attributes...")
for o, c in cls.items():
    ps = [p for p in G.neighbors(o) if G.nodes[p].get("type") == "parcel"]
    zips = Counter(situs_zip(G.nodes[p].get("situs","")) for p in ps)
    zips.pop("", None)
    addrs = sum(1 for a in G.neighbors(o) if G.nodes[a].get("type") == "address")
    G.nodes[o]["kind"] = c
    G.nodes[o]["total_parcels"] = len(ps)
    G.nodes[o]["total_value"] = sum(val(p) for p in ps)
    G.nodes[o]["n_addresses"] = addrs
    G.nodes[o]["n_zips"] = len(zips)
    G.nodes[o]["top_zip"] = zips.most_common(1)[0][0] if zips else None

print("\nadding same_mail edges (group capped at 15)...")
added_mail = 0
for a, d in G.nodes(data=True):
    if d.get("type") != "address": continue
    owners = [u for u in G.neighbors(a) if G.nodes[u].get("type") == "owner"]
    if not (2 <= len(owners) <= 15): continue
    for i in range(len(owners)):
        for j in range(i+1, len(owners)):
            u, v = owners[i], owners[j]
            if G.has_edge(u, v):
                G[u][v].setdefault("mail_count", 0)
                G[u][v]["mail_count"] += 1
            else:
                G.add_edge(u, v, relation="same_mail", mail_count=1)
                added_mail += 1
print(f"  added {added_mail:,} same_mail edges")

print("\nadding transfer edges and counterpart attributes...")
added_tx = 0
t_in  = Counter()
t_out = Counter()
for u, v, d in T.edges(data=True):
    t_out[u] += d.get("weight", 1)
    t_in[v]  += d.get("weight", 1)
    if u in G and v in G:
        w = d.get("weight", 1)
        if G.has_edge(u, v):
            G[u][v].setdefault("tx_weight", 0)
            G[u][v]["tx_weight"] += w
        else:
            G.add_edge(u, v, relation="sold_to", tx_weight=w)
            added_tx += 1
for n in G.nodes:
    if n.startswith("owner|"):
        G.nodes[n]["transfer_in"]  = t_in.get(n, 0)
        G.nodes[n]["transfer_out"] = t_out.get(n, 0)
print(f"  added {added_tx:,} sold_to edges")

out = os.path.expanduser("~/Desktop/cuyahoga_unified.pkl")
pickle.dump(G, open(out, "wb"))
print(f"\nwrote {out}: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

print("\nTOP 15 PERSONS by parcels")
persons = [(n, G.nodes[n]) for n in G.nodes if G.nodes[n].get("kind") == "person"]
persons.sort(key=lambda x: -x[1].get("total_parcels", 0))
for n, d in persons[:15]:
    print(f"  {d.get('total_parcels',0):4d}p  {d.get('transfer_in',0):4d}in "
          f"{d.get('transfer_out',0):4d}out  {n[6:][:60]}")

print("\nTOP 10 ENTITIES WITH A SAME_MAIL OR SOLD_TO EDGE")
linked = [(n, G.nodes[n]) for n in G.nodes
          if G.nodes[n].get("kind") == "entity"
          and any(G[u][v].get("relation") in ("same_mail","sold_to")
                  for u,v in G.edges(n))]
linked.sort(key=lambda x: -x[1].get("total_parcels", 0))
for n, d in linked[:10]:
    print(f"  {d.get('total_parcels',0):4d}p  {n[6:][:60]}")
