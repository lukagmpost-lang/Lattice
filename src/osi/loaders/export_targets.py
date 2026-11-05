import pickle, os, json

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
targets = []
seen = set()

for n, d in G.nodes(data=True):
    if d.get("voter_match") in ("name_unique", "dob", "address") and n.startswith("owner|"):
        # Skip if we already added this node
        if n in seen: continue
        
        name = n[6:] # Remove owner|
        
        # Try to parse first/last from "LAST, FIRST" or "FIRST LAST"
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
                continue # Skip single names
                
        if first and last:
            targets.append({"node_key": n, "last": last, "first": first})
            seen.add(n)

json.dump(targets, open(os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/data/scrape_targets_29k.json"), "w"))
print(f"Exported {len(targets):,} targets to ~/Desktop/OSI/Open-Source-Intelligence/data/scrape_targets_29k.json")
