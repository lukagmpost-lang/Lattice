import pickle, os, json

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
targets = []
seen = set()

for n, d in G.nodes(data=True):
    if d.get("voter_match") in ("unique", "address") and n.startswith("owner|"):
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

json.dump(targets, open(os.path.expanduser("~/Desktop/scrape_targets_full.json"), "w"))
print(f"Exported {len(targets):,} targets to ~/Desktop/scrape_targets_full.json")
