import pickle, os
from collections import Counter

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

person_edges = []
for n in G.nodes:
    if not n.startswith("owner|"): continue
    person_nb = 0
    for nb in G.neighbors(n):
        if nb.startswith("owner|"):
            rel = G[n][nb].get("relation", "")
            if rel in ("married_to", "divorced_from", "litigated_with", "mentioned_in_case"):
                person_nb += 1
    if person_nb >= 5:
        person_edges.append((person_nb, n[6:]))

person_edges.sort(reverse=True)

print(f"Nodes with 5+ person-to-person edges: {len(person_edges)}")
print(f"{'Edges':<6} {'Name'}")
print("-" * 50)
for count, name in person_edges[:30]:
    print(f"{count:<6} {name}")
