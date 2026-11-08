import pickle, os, json

def run():
    G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
    targets = []
    seen = set()

    for n, d in G.nodes(data=True):
        if d.get("voter_match") in ("name_unique", "dob", "address") and n.startswith("owner|"):
            if n in seen: continue
            name = n[6:] 
            if "," in name:
                parts = name.split(",")
                last = parts[0].strip()
                first = parts[1].strip().split()[0] if len(parts) > 1 else ""
            else:
                parts = name.split()
                if len(parts) > 1:
                    first = parts[0].strip()
                    last = parts[-1].strip()
                else:
                    continue
            if first and last:
                targets.append({"node_key": n, "last": last, "first": first})
                seen.add(n)

    out_path = os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/data/scrape_targets_29k.json")
    json.dump(targets, open(out_path, "w"))
    print(f"Exported {len(targets):,} targets to {out_path}")

if __name__ == "__main__":
    run()
