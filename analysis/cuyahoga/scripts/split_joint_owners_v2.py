"""Extended joint-owner splitter. Handles three-way joints and reversed order.

Patterns:
  A AND B, A & B       -- two parties
  A, B & C, A & B & C  -- three parties
  A AND B AND C        -- three parties

Surname inference: if one side is a bare first name, infer surname from
the other side. If both sides are bare first names, skip (ambiguous).
"""
import os, pickle, re

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

CORP_TOKENS = ('LLC', 'LTD', 'INC', 'CORP', 'LP', 'LLP', 'CO', 'COMPANY', 'TRUST', 'PARTNERS', 'ASSOCIATION')

def _is_corp(name):
    n = name.upper()
    return any(t in n.split() for t in CORP_TOKENS) or any(t in n for t in CORP_TOKENS)

def _surname(name):
    return name.split(',', 1)[0].strip() if ',' in name else None

def _infer_name(part, other):
    """If part is a bare first name, combine with other's surname."""
    part = part.strip().rstrip(',')
    if ',' in part or ' ' in part:
        return part
    sn = _surname(other)
    if sn: return f'{sn}, {part}'
    return part

def split_owner(name):
    n = name.strip()
    # Three-way split
    m3 = re.match(r'^(.+?)\s*(?:AND|&)\s*(.+?)\s*(?:AND|&)\s*(.+)$', n)
    if m3:
        parts = [m3.group(1).strip(), m3.group(2).strip(), m3.group(3).strip()]
        if any(len(p) < 2 for p in parts): return None
        if any(_is_corp(p) for p in parts): return None
        # infer surnames
        with_surname = [p for p in parts if _surname(p)]
        if len(with_surname) < 1: return None
        ref = with_surname[0]
        return tuple(_infer_name(p, ref) for p in parts)
    # Two-way split
    m2 = re.match(r'^(.+?)\s*(?:AND|&)\s*(.+)$', n)
    if m2:
        a, b = m2.group(1).strip(), m2.group(2).strip()
        if len(a) < 2 or len(b) < 2: return None
        if _is_corp(a) or _is_corp(b): return None
        # both have comma -- clean
        if ',' in a and ',' in b:
            return (a, b)
        # one has comma, other bare
        if ',' in a and ' ' not in b:
            return (a, _infer_name(b, a))
        if ',' in b and ' ' not in a:
            return (_infer_name(a, b), b)
        return None
    return None

candidates = []
for o in G.nodes:
    if not o.startswith("owner|"): continue
    name = o[6:]
    if not any(k in name.upper() for k in (" AND ", " & ")): continue
    parts = split_owner(name)
    if parts:
        candidates.append((o, name, parts))

print(f"candidates: {len(candidates):,}")
for o, name, parts in candidates[:15]:
    print(f"  {name[:60]:60s} -> {parts}")

splits = 0
new_nodes = 0
new_edges = 0
for old_key, old_name, parts in candidates:
    parcels = [p for p in G.neighbors(old_key) if p.startswith("parcel|")]
    if not parcels: continue
    keys = [f"owner|{_u(p)}" for p in parts]
    for k, nm in zip(keys, parts):
        if k not in G:
            G.add_node(k, type="owner", kind="person", name=nm,
                       source="split_from_joint", source_mentions=[old_name])
            new_nodes += 1
        else:
            G.nodes[k].setdefault("source_mentions", [])
            if old_name not in G.nodes[k]["source_mentions"]:
                G.nodes[k]["source_mentions"].append(old_name)
    for p in parcels:
        w = G[old_key][p].get("weight", 1) / len(keys)
        for k in keys:
            if not G.has_edge(k, p):
                G.add_edge(k, p, relation="owns", weight=w, source="split_from_joint")
    # all-pairs co_owner edges
    for i, a in enumerate(keys):
        for b in keys[i+1:]:
            if not G.has_edge(a, b):
                G.add_edge(a, b, relation="co_owner", weight=len(parcels), source="split_from_joint")
                new_edges += 1
    splits += 1

pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
print(f"\nsplits: {splits:,}")
print(f"new owner nodes: {new_nodes:,}")
print(f"new co_owner edges: {new_edges:,}")
print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
co = sum(1 for _, _, d in G.edges(data=True) if d.get("relation") == "co_owner")
print(f"total co_owner edges now: {co:,}")
