"""Split joint-owner strings into separate owner nodes and add co_owner edges.

Handles only mechanical patterns. Skips anything ambiguous.
Preserves the original joint string as a source_mentions attribute.
"""
import os, pickle, re
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

# Patterns tried in order. Each returns (name1, name2) or None.
CORP_TOKENS = ('LLC', 'LTD', 'INC', 'CORP', 'LP', 'LLP', 'CO', 'COMPANY', 'TRUST', 'PARTNERS')

def _is_corp(name):
    n = name.upper()
    return any(t in n.split() or t in n for t in CORP_TOKENS)

def _surname(name):
    # return the part before the first comma (LAST in LAST, FIRST)
    return name.split(',', 1)[0].strip() if ',' in name else None

def split_two(a, b):
    a, b = a.strip().rstrip(','), b.strip().rstrip(',')
    # reject if either side is a single letter or corporate entity
    if len(a) < 2 or len(b) < 2: return None
    if _is_corp(a) or _is_corp(b): return None
    # both look like LAST, FIRST
    if ',' in a and ',' in b:
        return (a, b)
    # first has comma (last, first), second is single-word (spouse first name)
    if ',' in a and ' ' not in b and b.isalpha():
        # infer surname from first party
        sn = _surname(a)
        return (a, f'{sn}, {b}' if sn else b)
    # first is single word, second has comma
    if ' ' not in a and a.isalpha() and ',' in b:
        sn = _surname(b)
        return (f'{sn}, {a}' if sn else a, b)
    return None

def split_owner(name):
    n = name.strip()
    # Case 1: A AND B (both sides look like names)
    m = re.match(r'^(.+?) (?:AND|&) (.+)$', n)
    if m:
        parts = split_two(m.group(1), m.group(2))
        if parts: return parts
    # Case 2: A, B, C (all comma-separated, each with own last-first)
    # too risky, skip
    return None

# Find owner nodes that look like joint strings
candidates = []
for o in G.nodes:
    if not o.startswith("owner|"): continue
    name = o[6:]
    if not any(k in name.upper() for k in (" AND ", " & ")): continue
    parts = split_owner(name)
    if parts:
        candidates.append((o, name, parts))

print(f"joint-owner candidates: {len(candidates):,}")
for o, name, parts in candidates[:10]:
    print(f"  {name[:60]:60s} -> {parts}")

# Build new nodes and edges
splits = 0
new_owner_nodes = 0
new_co_owner_edges = 0
parcels_split = set()

for old_key, old_name, (a, b) in candidates:
    # get the parcels this owner holds
    parcels = [p for p in G.neighbors(old_key) if p.startswith("parcel|")]
    if not parcels: continue
    a_key = f"owner|{_u(a)}"
    b_key = f"owner|{_u(b)}"
    # create nodes if missing
    for k, nm in [(a_key, a), (b_key, b)]:
        if k not in G:
            G.add_node(k, type="owner", kind="person", name=nm,
                       source="split_from_joint",
                       source_mentions=[old_name])
            new_owner_nodes += 1
        else:
            G.nodes[k].setdefault("source_mentions", [])
            if old_name not in G.nodes[k]["source_mentions"]:
                G.nodes[k]["source_mentions"].append(old_name)
    # add owns edges to each parcel
    for p in parcels:
        w = G[old_key][p].get("weight", 1) / 2
        for k in (a_key, b_key):
            if not G.has_edge(k, p):
                G.add_edge(k, p, relation="owns", weight=w, source="split_from_joint")
        parcels_split.add(p)
    # add co_owner edge between the split siblings
    if not G.has_edge(a_key, b_key):
        G.add_edge(a_key, b_key, relation="co_owner", weight=len(parcels), source="split_from_joint")
        new_co_owner_edges += 1
    splits += 1

pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))

print(f"\nsplit owners: {splits:,}")
print(f"new owner nodes: {new_owner_nodes:,}")
print(f"new co_owner edges: {new_co_owner_edges:,}")
print(f"parcels affected: {len(parcels_split):,}")
print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

# count co_owner edges now
co = sum(1 for u, v, d in G.edges(data=True) if d.get("relation") == "co_owner")
print(f"total co_owner edges now: {co:,}")
