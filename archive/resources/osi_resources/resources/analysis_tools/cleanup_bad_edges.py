import pickle, os

def run():
    G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
    removed = 0
    for u, v, d in list(G.edges(data=True)):
        if d.get("relation") in ("litigated_with", "mentioned_in_case"):
            caption = d.get("caption", "").lower()
            if u.startswith("owner|"):
                parts = u[6:].split(",")
                if len(parts) > 1:
                    last = parts[0].strip().lower()
                    first = parts[1].strip().split()[0].lower()
                    if last not in caption or first not in caption:
                        G.remove_edge(u, v)
                        removed += 1
    print(f"Removed {removed} false court edges.")
    pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))

if __name__ == "__main__":
    run()
