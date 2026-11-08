import pickle, os

def run():
    G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
    conflated = 0
    splits = 0
    
    for n in list(G.nodes):
        if not n.startswith("owner|"): continue
        spouses = []
        lawsuits = []
        
        for nb in G.neighbors(n):
            rel = G[n][nb].get("relation", "")
            if "married" in rel or "divorce" in rel:
                spouses.append(nb)
            elif "litigated" in rel or "mentioned" in rel:
                lawsuits.append(nb)
                
        if len(spouses) >= 4:
            base_name = n[6:]
            for i, spouse in enumerate(spouses[3:], start=2):
                new_node = f"owner|{base_name} ({i})"
                if new_node not in G:
                    G.add_node(new_node, type="owner", kind="person", name=f"{base_name} ({i})", source="court_record")
                G.add_edge(new_node, spouse, **G[n][spouse])
                G.remove_edge(n, spouse)
                splits += 1
            conflated += 1
        elif len(spouses) >= 2 and len(lawsuits) >= 10:
            G.nodes[n]["high_degree_warning"] = True
            
    print(f"Identified {conflated} conflated nodes and split them.")
    print(f"Performed {splits} edge splits.")
    pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))

if __name__ == "__main__":
    run()
