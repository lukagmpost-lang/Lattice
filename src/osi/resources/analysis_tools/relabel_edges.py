import pickle, os

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
relabeled = 0

for u, v, d in G.edges(data=True):
    if d.get("relation") in ("litigated_with", "divorced_from"):
        caption = d.get("caption", "").lower()
        u_last = u.split(",")[0].replace("owner|", "").replace("org|", "").strip().lower()
        v_last = v.split(",")[0].replace("owner|", "").replace("org|", "").strip().lower()
        
        if u_last not in caption and v_last not in caption:
            d["relation"] = "mentioned_in_case"
            relabeled += 1

print(f"Relabeled {relabeled} edges as mentioned_in_case.")
pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
