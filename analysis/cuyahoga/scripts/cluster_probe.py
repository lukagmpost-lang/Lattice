import os, pickle, re
from collections import defaultdict

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

CLUSTER = ["SHAMSSHARE", "SHAMSHARE", "DEEN KALA", "JAMSERIES", "URBANSTAY",
           "FROMBY", "9LYVES"]

def matches_cluster(name):
    n = _u(name)
    return any(k in n for k in CLUSTER)

# Every parcel whose owner matches any cluster member
parcels = set()
owners_by_parcel = defaultdict(list)
for n, d in G.nodes(data=True):
    if not n.startswith("owner|"): continue
    if not matches_cluster(n[6:]): continue
    for p in G.neighbors(n):
        if G.nodes[p].get("type") == "parcel":
            parcels.add(p)
            owners_by_parcel[p].append(n[6:])

print(f"cluster members: {len([n for n in G.nodes if n.startswith('owner|') and matches_cluster(n[6:])])} owners")
print(f"unique parcels across cluster: {len(parcels)}")

# Get deed references for each parcel
book_pages = []
for p in parcels:
    d = G.nodes[p]
    bp = d.get("book_page", "")
    pid = d.get("pid", "")
    if bp and bp.strip():
        book_pages.append((pid, bp, d.get("last_transfer_date"), owners_by_parcel[p]))

print(f"parcels with book_page: {len(book_pages)}/{len(parcels)}")
print(f"\nSample 20 (for deed lookup at recorder):")
for pid, bp, date, owners in book_pages[:20]:
    print(f"  {pid}  book {bp:20s}  {date or 'n/a':10s}  {owners[0][:40]}")

# Save the full list for the recorder lookup
import json
out = os.path.expanduser("~/Desktop/cluster_deeds.json")
json.dump([{"parcel_id": pid, "book_page": bp, "date": date, "owners": owners}
           for pid, bp, date, owners in book_pages], open(out, "w"), indent=1)
print(f"\nwrote {out}: {len(book_pages)} parcels with deed refs")
