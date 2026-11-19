import os, pickle, re
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

TRUSTEE_RE = re.compile(r"\(TRS\)|\(TRUSTEE\)|- ?TRUSTEE|CO-?TRUSTEE|\bTRUSTEE\b|\bSUC-?TRS\b")
PLACEHOLDER = {"VACANT LOT","VACANT LAND","SEE PARCEL","NONE","UNKNOWN","NULL","","TBD","UNKNOWN OWNER"}

# Both startswith-prefixes and in-string substrings
GOV_PREFIX = ("CITY OF","CITY ","VILLAGE OF","STATE OF","COUNTY OF","TOWNSHIP OF",
              "BOARD OF","UNITED STATES","U S A","SECRETARY OF","DEPARTMENT OF",
              "DISTRICT OF")
ENTITY_SUBSTR = (
    " LLC"," L.L.C"," CORP"," INC"," INCORPORATED"," L.P"," LLP","LTD"," LIMITED",
    " COMPANY"," CO."," PARTNERSHIP"," PARTNERS"," HOLDINGS"," PROPERTIES",
    " REALTY"," DEVELOPMENT"," FUND"," BANK"," CREDIT UNION",
    " CHURCH"," DIOCESE"," BISHOP"," MINISTRIES"," HOSPITAL"," HEALTH"," CLINIC",
    " UNIVERSITY"," COLLEGE"," FOUNDATION"," SCHOOL"," LIBRARY"," ACADEMY",
    " AUTHORITY"," METRO"," PARK DIST"," HOUSING"," CONSERVANCY"," RTA",
    " HABITAT"," HUMANITY"," NEIGHBORHOOD"," CDC",
    " MHC"," MHP"," ASSN"," ASSOC"," TRUST CO",
    " HOMES"," ESTATES"," RESERVE"," CASE WESTERN"," LAND CO"," PARK ",
)
LAST_TOKEN_ENTITY = {"LP","LLC","LLP","LTD","CO","INC","CORP","PC","PLLC","TRUST","L.P.","L.L.C.","CDC"}

def classify(name):
    n = _u(name)
    for sfx in (" ET AL"," ET UX"," ET VIR"):
        if n.endswith(sfx): n = n[:-len(sfx)].strip()
    if not n: return "unknown"
    if n in PLACEHOLDER or n.startswith("SEE PARCEL"): return "placeholder"
    if TRUSTEE_RE.search(n): return "trust"
    if any(n.startswith(p) for p in GOV_PREFIX): return "entity"
    if any(k in n for k in ENTITY_SUBSTR): return "entity"
    toks = n.split()
    if toks and toks[-1].strip(".,") in LAST_TOKEN_ENTITY: return "entity"
    # "CLEVELAND ,CITY OF LB94" style — comma-space artifacts
    if re.search(r",\s*CITY|\bCITY\b|\bLB\d+", n): return "entity"
    if "," in n:
        head = n.split(",",1)[0].strip()
        if head and re.match(r"^[A-Z][A-Z .'-]+$", head) and len(head.split()) <= 3:
            return "person"
    if 2 <= len(toks) <= 3 and all(len(t) >= 2 and re.match(r"^[A-Z][A-Z.'-]*$", t) for t in toks):
        return "person"
    return "unknown"

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
T = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_transfers.pkl"), "rb"))
LB = "LAND REUTILIZATION"

before = Counter(G.nodes[n].get("kind","?") for n in G.nodes if n.startswith("owner|"))
for n in G.nodes:
    if n.startswith("owner|"):
        G.nodes[n]["kind"] = classify(n[6:])
after = Counter(G.nodes[n].get("kind","?") for n in G.nodes if n.startswith("owner|"))

print("=== CLASSIFIER v5 ===")
for k in ("person","entity","trust","placeholder","unknown"):
    d = after.get(k,0) - before.get(k,0)
    print(f"  {k:12s} {before.get(k,0):6d} -> {after.get(k,0):6d}  ({d:+d})")

print("\n=== TOP 15 PEOPLE (person/trust only) ===")
persons = []
for n, d in G.nodes(data=True):
    if d.get("kind") in ("person","trust") and n.startswith("owner|"):
        ps = [x for x in G.neighbors(n) if G.nodes[x].get("type") == "parcel"]
        if ps: persons.append((n, len(ps), d["kind"]))
persons.sort(key=lambda x: -x[1])
for n, c, k in persons[:15]:
    print(f"  {c:4d}  [{k:6s}]  {n[6:][:60]}")

print("\n=== TOP 15 FLIPPERS, entity-only (exclude govt/nonprofit already LB) ===")
lb_acquirers = set()
for u, v, d in T.edges(data=True):
    if LB in _u(u): lb_acquirers.add(v)

flips = Counter()
for u, v, d in T.edges(data=True):
    if u in lb_acquirers and LB not in _u(v) and v not in lb_acquirers:
        flips[u] += d.get("weight", 1)

for n, c in flips.most_common(25):
    kind = G.nodes[n].get("kind","transfer_only") if n in G else "transfer_only"
    print(f"  {c:4d} resold  [{kind:13s}]  {n[6:][:60]}")

pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
