"""Load the five confirmed deed signatories as person->entity edges.

Each entry is (person_name, entity_name, role, book_page, source_note).
The five deeds were pulled from cuyahoga.oh.publicsearch.us on 2026-11-02.
These edges are ground truth for testing link prediction.
"""
import os, pickle, re

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

SIGNATORIES = [
    # (person, entity, role, book_page, note)
    ("MAX LOMAS", "JANA PROPERTIES, LLC", "sole_member",
     "202501070252", "signed for JANA PROPERTIES -> SHAMSSHARE ALLY"),
    ("DEREK KRAMER", "KEYBANK NATIONAL ASSOCIATION", "section_leader",
     "201604190761", "signed for KEYBANK -> Shamsshare Ally"),
    ("JOE LIU", "JAMSERIES, LLC", "sole_member_via_orangerock",
     "202412170133", "signed for Joe+Liu+to+JAMSERIES, and for JAMSERIES->ALLY (via ORANGEROCK)"),
    ("AMY LIU", "JAMSERIES, LLC", "co_grantor_personal",
     "202412170133", "signed as personal grantor for JAMSERIES"),
    ("DUANE E. BREMKE", "FREEDOM ESTATES LTD", "managing_member",
     "202607310445", "signed for FREEDOM ESTATES -> DEEN KALA"),
]

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

def find_owner_node(entity_name):
    """Find the graph's owner| or entity| node matching this entity string."""
    target = _u(entity_name)
    # exact
    for prefix in ("entity|", "owner|"):
        key = f"{prefix}{target}"
        if key in G: return key
    # substring match
    for n in G.nodes:
        if n.startswith(("entity|", "owner|")) and target in _u(n):
            return n
    return None

added_people = added_edges = 0
for person_name, entity_name, role, book_page, note in SIGNATORIES:
    pn = _u(person_name)
    pk = f"person|{pn}"
    if pk not in G:
        G.add_node(pk, type="person", name=pn, source="manual_deed")
        added_people += 1
    ent = find_owner_node(entity_name)
    if ent is None:
        print(f"  [skip] entity not found: {entity_name}")
        continue
    if G.has_edge(pk, ent):
        G[pk][ent].setdefault("sources", [])
        if "manual_deed" not in G[pk][ent]["sources"]:
            G[pk][ent]["sources"].append("manual_deed")
    else:
        G.add_edge(pk, ent, relation="signed_for", role=role,
                   book_page=book_page, source="manual_deed", note=note)
        added_edges += 1
    print(f"  linked {pn} -> {ent[6:][:40]} ({role})")

pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
print(f"\nadded {added_people} person nodes, {added_edges} signed_for edges")
print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
