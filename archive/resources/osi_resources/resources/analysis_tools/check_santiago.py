import pickle, os
G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

target = "owner|SANTIAGO, JAMES D"
if target not in G:
    print(f"{target} not found.")
    # check for period variants
    for n in G.nodes:
        if n.startswith("owner|SANTIAGO, JAMES D"):
            print(f"Found variant: {n}")
            target = n
            break

if target in G:
    print(f"\nNeighbors of {target}:")
    for nb in G.neighbors(target):
        d = G[target][nb]
        print(f"  - {nb[6:50]:40s} | {d.get('relation')} | {d.get('case_no', '')}")
