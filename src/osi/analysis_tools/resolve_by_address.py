import pickle, os
import networkx as nx

def run():
    G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
    split_count = 0
    
    for n in list(G.nodes):
        if not n.startswith("owner|"): continue
        addr = G.nodes[n].get("residential_address")
        if not addr or "," not in addr: continue
        nz = addr.split(",")[-1].strip()[:5]
        
        for nb in list(G.neighbors(n)):
            rel = G[n][nb].get("relation", "")
            if "married" in rel or "divorce" in rel:
                spouse_addr = G.nodes[nb].get("residential_address")
                if not spouse_addr or "," not in spouse_addr: continue
                nbz = spouse_addr.split(",")[-1].strip()[:5]
                
                if nz != nbz:
                    n_p = {p for p in G.neighbors(n) if p.startswith("parcel|")}
                    nb_p = {p for p in G.neighbors(nb) if p.startswith("parcel|")}
                    if not (n_p & nb_p):
                        new_node = f"{n} (zip_{nbz})"
                        if new_node not in G:
                            G.add_node(new_node, type="owner", kind="person", name=f"{n[6:]} (zip_{nbz})", source="address_split")
                        G.add_edge(new_node, nb, **G[n][nb])
                        G.remove_edge(n, nb)
                        split_count += 1

    print(f"Split {split_count} edges based on ZIP mismatch.")
    pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))

if __name__ == "__main__":
    run()
