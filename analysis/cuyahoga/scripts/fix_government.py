import os, pickle, re
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

# Governments already in the graph: reclassify anything matching these patterns
GOV_PATTERNS = [
    re.compile(r"\bCITY OF\b"),                # "CLEVELAND CITY OF", "PARMA CITY OF"
    re.compile(r"\bCITY OF [A-Z]"),            # "CITY OF CLEVELAND"
    re.compile(r"^[A-Z][A-Z .'-]+\sCITY\s*$"), # "CLEVELAND CITY"
    re.compile(r"\bSTATE OF\b"),               # "STATE OF OHIO"
    re.compile(r"^OHIO STATE\b"),              # "OHIO STATE OF HGY"
    re.compile(r"\bCOUNTY OF\b"),
    re.compile(r"\bVILLAGE OF\b"),
    re.compile(r"\bTOWNSHIP OF\b"),
    re.compile(r"\bLAND REUTILIZATION\b"),     # all land banks
    re.compile(r"\bLAND REUTILZATION\b"),
    re.compile(r"\bLAND REUTLIZATION\b"),
    re.compile(r"\bLAND RETULIZATION\b"),
    re.compile(r"\bLAND TEUTILIZATION\b"),
    re.compile(r"\bLB\d+\b"),                   # "CLEVELAND CITY OF LB91"
    re.compile(r"\bL/B\b"),
    re.compile(r"\bSCHOOL DISTRICT\b"),
    re.compile(r"\bPUBLIC LIBRARY\b"),
    re.compile(r"^CLEVE PUBLIC LIBRARY"),
    re.compile(r"\bMETRO PARK\b"),
    re.compile(r"\bMET PK\b"),
    re.compile(r"\bPARK DIST\b"),
    re.compile(r"\bBOARD OF EDUCATION\b"),
    re.compile(r"\bBOARD OF PARK\b"),
    re.compile(r"\bBD OF\b"),
    re.compile(r"\bCMHA\b"),
    re.compile(r"\bC\.M\.H\.A\.\b"),
    re.compile(r"\bU S A\b"),
    re.compile(r"^U\.S\.A\.?$"),
    re.compile(r"\bPORT AUTHORITY\b"),
    re.compile(r"\bTRANSIT AUTHORITY\b"),
    re.compile(r"\bRTA\b"),
    re.compile(r"^NEORSD\b"),
    re.compile(r"\bSEWER DISTRICT\b"),
]

# Things that should NOT be government even if they contain gov keywords
NOT_GOV = re.compile(r"\b(REAL ESTATE|REALTY|PROPERTIES|DEVELOPMENT|HOLDINGS|INVESTMENTS|LLC|INC|CORP|COMPANY)\b")

def is_government(name):
    n = _u(name)
    if NOT_GOV.search(n): return False
    return any(p.search(n) for p in GOV_PATTERNS)

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

before = Counter(d.get("kind","?") for n, d in G.nodes(data=True) if n.startswith("owner|"))
reclassified = 0
for n, d in G.nodes(data=True):
    if not n.startswith("owner|"): continue
    if d.get("kind") in ("government", "placeholder"): continue
    if is_government(n[6:]):
        d["kind"] = "government"
        reclassified += 1

after = Counter(d.get("kind","?") for n, d in G.nodes(data=True) if n.startswith("owner|"))

print(f"reclassified {reclassified} owners as government")
print("\nbefore:", dict(before))
print("after: ", dict(after))

# Recount top persons
persons = []
for n, d in G.nodes(data=True):
    if d.get("kind") in ("person","trust") and n.startswith("owner|"):
        ps = [p for p in G.neighbors(n) if G.nodes[p].get("type") == "parcel"]
        if ps: persons.append((n, len(ps), d["kind"]))
persons.sort(key=lambda x: -x[1])

print("\n=== TOP 20 PERSONS after fix ===")
for n, c, k in persons[:20]:
    print(f"  {c:4d}  [{k:6s}]  {n[6:][:60]}")

# Land bank after fix
LB_RE = re.compile(r"\bLAND REUTILIZATION\b|\bLAND REUTILZATION\b|\bLAND REUTLIZATION\b|\bLAND RETULIZATION\b|\bLAND TEUTILIZATION\b|\bLB\d+\b|\bL/B\b")
lb_parcels = set()
for n, d in G.nodes(data=True):
    if n.startswith("owner|") and LB_RE.search(_u(n[6:])):
        for p in G.neighbors(n):
            if G.nodes[p].get("type") == "parcel":
                lb_parcels.add(p)

print(f"\n=== LAND BANK: {len(lb_parcels):,} unique parcels ===")

# Private threshold sweep excluding ALL government
private = []
for n, d in G.nodes(data=True):
    if not n.startswith("owner|"): continue
    if d.get("kind") not in ("person","entity","trust"): continue
    ps = [p for p in G.neighbors(n) if G.nodes[p].get("type") == "parcel"]
    if ps: private.append((n, ps))

print("\n=== PRIVATE THRESHOLD SWEEP ===")
for thresh in (3, 5, 10, 20):
    owners_at = [(n, ps) for n, ps in private if len(ps) >= thresh]
    unique_p = set()
    for _, ps in owners_at: unique_p.update(ps)
    ratio = len(lb_parcels) / max(1, len(unique_p))
    print(f"  {thresh:2d}+ parcels: {len(owners_at):>5,} owners / {len(unique_p):>7,} parcels | LB/private: {ratio:.2f}")

pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
print("\nsaved")
