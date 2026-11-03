"""Test link prediction against the five deed signatory ground-truth edges.

For each known (person, entity) edge, temporarily remove it, run Adamic-Adar
over the person's neighborhood, and check whether the entity ranks in the top K.
"""
import os, pickle, sys
import networkx as nx

sys.path.insert(0, os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/src"))

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

# ground truth — the five signed_for edges
GROUND_TRUTH = [
    ("owner|MAX LOMAS", "owner|JANA PROPERTIES, LLC"),
    ("owner|DEREK KRAMER", "owner|KEYBANK NATIONAL ASSOCIATION"),
    ("owner|JOE LIU", "owner|JAMSERIES, LLC"),
    ("owner|AMY LIU", "owner|JAMSERIES, LLC"),
    ("owner|DUANE E. BREMKE", "owner|FREEDOM ESTATES LTD"),
]

def find_node(query):
    if query in G: return query
    q = query.split("|",1)[1].upper()
    for n in G.nodes:
        if n.startswith(query.split("|",1)[0] + "|") and q in n.upper():
            return n
    return None

print(f"Graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
print(f"Testing {len(GROUND_TRUTH)} ground-truth edges\n")

hits = 0
misses = 0
for person_str, ent_str in GROUND_TRUTH:
    pn = find_node(person_str)
    en = find_node(ent_str)
    if pn is None or en is None:
        print(f"  [skip] {person_str} or {ent_str} not found")
        continue
    # verify the edge exists
    if not G.has_edge(pn, en):
        print(f"  [skip] edge {pn} -> {en} not present (run load_deed_signatories.py first)")
        continue
    # Temporarily remove it to test whether AA would predict it
    edge_data = dict(G[pn][en])
    G.remove_edge(pn, en)
    # Adamic-Adar against all of pn's 2-hop neighbors, excluding immediate neighbors
    immediate = set(G.neighbors(pn))
    immediate.add(pn)
    candidates = []
    for n2 in G.neighbors(pn):
        for n3 in G.neighbors(n2):
            if n3 not in immediate and n3.startswith("owner|"):
                candidates.append((pn, n3))
    if not candidates:
        print(f"  [{pn[7:20]:15s}] no 2-hop candidates")
        G.add_edge(pn, en, **edge_data)
        misses += 1
        continue
    scores = list(nx.adamic_adar_index(G, candidates))
    scores.sort(key=lambda x: -x[2])
    top20 = [s[1] for s in scores[:20]]
    if en in top20:
        rank = top20.index(en) + 1
        hit_score = next(s[2] for s in scores if s[1] == en)
        print(f"  [HIT] {pn[7:22]:20s} predicted {en[6:30]:30s} at rank {rank} (score {hit_score:.3f})")
        hits += 1
    else:
        # what did it predict?
        top_names = [s[1][6:25] for s in scores[:3]]
        print(f"  [MISS] {pn[7:22]:20s} predicted {top_names} instead of {en[6:30]}")
        misses += 1
    G.add_edge(pn, en, **edge_data)

print(f"\n{hits} hits, {misses} misses out of {len(GROUND_TRUTH)}")
