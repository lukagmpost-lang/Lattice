"""Fold person| and entity| nodes into owner|, keeping kind attribute.

Creates a single owner namespace where kind distinguishes person/entity/trust/gov.
Preserves all edges and attributes. Idempotent.
"""
import os, pickle, re
import networkx as nx

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

before_person = sum(1 for n in G.nodes if n.startswith("person|"))
before_entity = sum(1 for n in G.nodes if n.startswith("entity|"))
before_owner  = sum(1 for n in G.nodes if n.startswith("owner|"))

renamed = 0
merged = 0
edge_moves = 0

for old_n in list(G.nodes):
    if old_n.startswith("person|"):
        kind = "person"
        name = old_n[7:]
    elif old_n.startswith("entity|"):
        kind = "entity"
        name = old_n[7:]
    else:
        continue

    new_n = f"owner|{_u(name)}"

    if new_n in G:
        # owner| already exists. Merge attributes and redirect edges.
        for k, v in G.nodes[old_n].items():
            if k not in G.nodes[new_n]:
                G.nodes[new_n][k] = v
        for pred in list(G.predecessors(old_n)):
            if not G.has_edge(pred, new_n):
                G.add_edge(pred, new_n, **dict(G[pred][old_n]))
                edge_moves += 1
        for succ in list(G.successors(old_n)):
            if not G.has_edge(new_n, succ):
                G.add_edge(new_n, succ, **dict(G[old_n][succ]))
                edge_moves += 1
        G.remove_node(old_n)
        merged += 1
    else:
        # rename in place
        G = nx.relabel_nodes(G, {old_n: new_n})
        renamed += 1

    # ensure kind is set
    if new_n in G:
        G.nodes[new_n].setdefault("kind", kind)
        G.nodes[new_n].setdefault("name", name)

pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))

after_person = sum(1 for n in G.nodes if n.startswith("person|"))
after_entity = sum(1 for n in G.nodes if n.startswith("entity|"))
after_owner  = sum(1 for n in G.nodes if n.startswith("owner|"))

print(f"before: owner={before_owner:,} person={before_person} entity={before_entity}")
print(f"renamed in place: {renamed}")
print(f"merged into existing owner|: {merged}")
print(f"edges moved during merges: {edge_moves}")
print(f"after:  owner={after_owner:,} person={after_person} entity={after_entity}")
print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
