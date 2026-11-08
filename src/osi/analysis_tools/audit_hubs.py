import pickle, os

def run():
    G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
    hubs = []
    for n in G.nodes:
        if not n.startswith("owner|"): continue
        edges = 0
        for nb in G.neighbors(n):
            if nb.startswith("owner|"):
                rel = G[n][nb].get("relation", "")
                if rel in ("married_to", "divorced_from", "litigated_with", "mentioned_in_case"):
                    edges += 1
        if edges >= 5:
            hubs.append((edges, n[6:]))
            
    hubs.sort(reverse=True)
    print(f"Nodes with 5+ person-to-person edges: {len(hubs)}\n")
    print(f"{'Edges':<6} {'Name'}")
    print("-" * 50)
    for count, name in hubs[:30]:
        print(f"{count:<6} {name}")

if __name__ == "__main__":
    run()
