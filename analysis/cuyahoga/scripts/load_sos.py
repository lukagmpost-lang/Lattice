import csv, os, pickle, re
import networkx as nx

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
path = os.path.expanduser("~/Desktop/sos_pass2.csv")
rows = list(csv.DictReader(open(path)))

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

added_e = added_a = 0
for r in rows:
    tax_name = _u(r.get("tax_roll_name"))
    eno = _u(r.get("entity_no"))
    if not tax_name or eno in ("NOT FOUND", ""): continue
    owner_key = f"owner|{tax_name}"
    ent_key = f"entity|OH{eno}"
    if ent_key not in G:
        G.add_node(ent_key, type="entity",
                   name=r.get("sos_name") or tax_name,
                   ohio_entity_no=eno,
                   entity_type=r.get("sos_type"),
                   filing_date=r.get("filed"),
                   home_state=r.get("home_state"),
                   source="ohio_sos")
        added_e += 1
    if owner_key in G:
        G.add_edge(owner_key, ent_key, relation="registered_as", source="ohio_sos")
        added_a += 1
    for field in ("registered_agent","officers"):
        val = _u(r.get(field))
        if not val: continue
        for name in re.split(r"\s*[;|]\s*", val):
            name = name.strip()
            if not name or len(name) < 3: continue
            pk = f"person|{name}"
            if pk not in G:
                G.add_node(pk, type="person", name=name, source="ohio_sos")
            rel = "registered_agent_of" if field == "registered_agent" else "officer_of"
            G.add_edge(pk, ent_key, relation=rel, source="ohio_sos")

pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
print(f"entities added: {added_e}, links: {added_a}")
print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
print(f"nodes by type: person={sum(1 for _,d in G.nodes(data=True) if d.get('type')=='person')}, "
      f"entity={sum(1 for _,d in G.nodes(data=True) if d.get('type')=='entity')}")
