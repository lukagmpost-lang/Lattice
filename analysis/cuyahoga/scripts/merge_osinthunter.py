import sqlite3, pickle, os, re, json

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
conn = sqlite3.connect(os.path.expanduser("~/Desktop/OsintHunter/data/osint.db"))
cur = conn.cursor()

rows = cur.execute("SELECT id, value, attrs FROM entities WHERE type='person'").fetchall()
print(f"person entities: {len(rows)}")

added_aliases = 0
added_dorks = 0
for pid, name, attrs_raw in rows:
    attrs = json.loads(attrs_raw) if attrs_raw else {}
    target = f"owner|{_u(name)}"
    if target not in G:
        for n in G.nodes:
            if n.startswith("owner|") and _u(name) in n:
                target = n; break
        else:
            print(f"  no match in graph: {name}")
            continue
    print(f"  matched: {name} -> {target}")
    for alias in attrs.get("_candidatos", []):
        ak = f"owner|{_u(alias)}"
        if ak not in G:
            G.add_node(ak, type="owner", kind="person", name=alias, source="osinthunter_alias")
        if not G.has_edge(target, ak):
            G.add_edge(target, ak, relation="has_alias", source="osinthunter")
            added_aliases += 1
    # store dorks as a node attribute, not edges
    if "_dorks" in attrs:
        G.nodes[target]["osinthunter_dorks"] = len(attrs["_dorks"])
        added_dorks += len(attrs["_dorks"])
    if "_links" in attrs:
        G.nodes[target]["osinthunter_links"] = attrs["_links"]

pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
print(f"\nadded {added_aliases} has_alias edges")
print(f"stored {added_dorks} dork URLs on matched nodes")
print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
