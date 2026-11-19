import os, pickle, re, json, sqlite3

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
conn = sqlite3.connect(os.path.expanduser("~/Desktop/OsintHunter/data/osint.db"))
cur = conn.cursor()

owner_index = {}
for n in G.nodes:
    if n.startswith("owner|") and G.nodes[n].get("queryable") is not False:
        owner_index.setdefault(_u(n[6:]), n)
print(f"owner index: {len(owner_index):,} keys")

rows = cur.execute("SELECT id, value, attrs FROM entities WHERE type='person'").fetchall()
print(f"person entities: {len(rows)}")

added_aliases = 0
added_dorks = 0
unmatched = []

for pid, name, attrs_raw in rows:
    attrs = json.loads(attrs_raw) if attrs_raw else {}
    key = _u(name)
    target = owner_index.get(key)
    if target is None:
        hits = [v for k, v in owner_index.items() if key in k]
        if len(hits) == 1:
            target = hits[0]
        elif len(hits) > 1:
            print(f"  AMBIGUOUS: {name} -> {len(hits)} matches, skipping")
            unmatched.append((name, "ambiguous"))
            continue
        else:
            print(f"  no match: {name}")
            unmatched.append((name, "none"))
            continue
    print(f"  matched: {name} -> {target}")
    for alias in attrs.get("_candidatos", []):
        ak = f"owner|{_u(alias)}"
        if ak not in G:
            G.add_node(ak, type="owner", kind="person", name=alias, source="osinthunter_alias")
        if not G.has_edge(target, ak):
            G.add_edge(target, ak, relation="has_alias", source="osinthunter")
            added_aliases += 1
    if "_dorks" in attrs:
        G.nodes[target]["osinthunter_dorks"] = len(attrs["_dorks"])
        added_dorks += len(attrs["_dorks"])
    if "_links" in attrs:
        G.nodes[target]["osinthunter_links"] = attrs["_links"]

pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
print(f"\nadded {added_aliases} has_alias edges")
print(f"stored {added_dorks} dork URLs on matched nodes")
print(f"unmatched: {len(unmatched)}")
for name, why in unmatched:
    print(f"  [{why}] {name}")
print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
