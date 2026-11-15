import os, pickle, re
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\\s+"," ",str(s)).strip().upper()

_CACHE = None
_OWN_COUNTS = None

def load():
    global _CACHE, _OWN_COUNTS
    if _CACHE is None:
        _CACHE = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
        _OWN_COUNTS = []
        for n in _CACHE.nodes:
            if not n.startswith("owner|"): continue
            c = sum(1 for p in _CACHE.neighbors(n) if _CACHE.nodes[p].get("type") == "parcel")
            _OWN_COUNTS.append((n, c))
        _OWN_COUNTS.sort(key=lambda x: -x[1])
    return _CACHE

def find_person(query):
    G = load()
    q = _u(query)
    exact_key = f"owner|{q}"
    if exact_key in G:
        return _dossier(exact_key)
    for n, d in G.nodes(data=True):
        if n.startswith("owner|") and G.nodes[n].get("queryable") is not False:
            if q in n:
                return _dossier(n)
    return {"error": f"no owner found matching '{query}'"}

def _dossier(node_key):
    G = load()
    d = G.nodes[node_key]
    name = node_key[6:]
    parcels = [p for p in G.neighbors(node_key) if G.nodes[p].get("type") == "parcel"]
    addrs = [a for a in G.neighbors(node_key) if G.nodes[a].get("type") == "address"]
    rank = next((i + 1 for i, (n, _c) in enumerate(_OWN_COUNTS) if n == node_key), None)
    total_owners = len(_OWN_COUNTS)
    return {
        "name": name,
        "kind": d.get("kind", "unknown"),
        "total_parcels": len(parcels),
        "rank_among_owners": f"#{rank} of {total_owners:,}" if rank else "n/a",
        "date_of_birth": d.get("date_of_birth"),
        "residential_address": d.get("residential_address"),
        "voter_match": d.get("voter_match"),
    }

def render(dossier):
    if "error" in dossier: return dossier["error"]
    out = []
    out.append(f"{dossier['name']}  [{dossier['kind']}]")
    out.append("=" * 60)
    if dossier.get("date_of_birth"):
        out.append(f"  DOB:     {dossier['date_of_birth']}")
    if dossier.get("residential_address"):
        out.append(f"  address: {dossier['residential_address']}")
    out.append(f"  parcels: {dossier['total_parcels']}")
    out.append(f"  rank:    {dossier['rank_among_owners']}")
    return "\\n".join(out)

if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:])
    print(render(find_person(q)))
