import pickle, os

def run():
    G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
    ADMIN_KEYWORDS = [
        "TREASURER OF CUYAHOGA", "STATE OF OHIO", "CITY OF CLEVELAND", 
        "CUYAHOGA COUNTY", "DEPARTMENT OF TAXATION", "LAND REUTILIZATION",
        "HOUSING AUTHORITY", "METROPOLITAN HOUSING"
    ]
    removed = 0
    for u, v, d in list(G.edges(data=True)):
        if d.get("relation") in ("litigated_with", "mentioned_in_case"):
            caption = d.get("caption", "").upper()
            if any(kw in caption for kw in ADMIN_KEYWORDS):
                G.remove_edge(u, v)
                removed += 1
    print(f"Removed {removed} administrative/government court edges.")
    pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))

if __name__ == "__main__":
    run()
