import pickle, os
import networkx as nx

print("Loading graph...")
G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
print("Resolving social edges by Voter File Address mismatch...")

split_count = 0
checked_count = 0

for n in list(G.nodes):
    if not n.startswith("owner|"): continue
    node_zip = None
    addr = G.nodes[n].get("residential_address")
    if addr and "," in addr:
        node_zip = addr.split(",")[-1].strip()[:5]
    if not node_zip: continue

    for nb in list(G.neighbors(n)):
        rel = G[n][nb].get("relation", "")
        if "married" in rel or "divorce" in rel:
            checked_count += 1
            spouse_addr = G.nodes[nb].get("residential_address")
            if not spouse_addr or "," not in spouse_addr:
                continue
            spouse_zip = spouse_addr.split(",")[-1].strip()[:5]
            if node_zip != spouse_zip:
                n_parcels = {p for p in G.neighbors(n) if p.startswith("parcel|")}
                nb_parcels = {p for p in G.neighbors(nb) if p.startswith("parcel|")}
                if not (n_parcels & nb_parcels):
                    new_node = f"{n} (zip_{spouse_zip})"
                    if new_node not in G:
                        G.add_node(new_node, type="owner", kind="person", name=f"{n[6:]} (zip_{spouse_zip})", source="address_split")
                    G.add_edge(new_node, nb, **G[n][nb])
                    G.remove_edge(n, nb)
                    split_count += 1
                    print(f"Split {n[6:]} <-> {nb[6:]} (ZIP {node_zip} != {spouse_zip})")

print(f"\nChecked {checked_count} marriage/divorce edges.")
print(f"Split {split_count} edges based on address mismatch.")
pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
print("Graph saved.")
