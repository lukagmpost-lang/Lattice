import pickle, os
import networkx as nx

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

ENTITY_KEYWORDS = {
    "BANK", "LLC", "INC", "CORP", "ASSN", "ASSOCIATION", "CO", "COMPANY", 
    "COUNTY", "TREASURER", "STATE", "CITY", "OHIO", "TRUST", "CREDIT", 
    "UNION", "FEDERAL", "SAVINGS", "LOAN", "FINANCIAL", "MORTGAGE", 
    "SERVICE", "SERVICES", "GROUP", "PARTNERS", "LP", "LTD", "P.C.", 
    "ESTATE", "PROPERTIES", "REALTY", "ADJUSTMENT", "ENTERPRISES",
    "HOSPITAL", "MEDICAL", "HEALTH", "CENTER", "CLINIC", "PHYSICIANS", 
    "SURGERY", "CARE", "UNIVERSITY", "COLLEGE", "SCHOOL",
    "AUTHORITY", "TRANSIT", "EDUCATION", "BOARD", "CAPITAL"
}

mapping = {}
for n in G.nodes:
    if n.startswith("owner|"):
        upper_n = n.upper()
        if any(kw in upper_n for kw in ENTITY_KEYWORDS):
            mapping[n] = n.replace("owner|", "org|")

if mapping:
    G = nx.relabel_nodes(G, mapping)
    for old_n, new_n in mapping.items():
        G.nodes[new_n]["type"] = "org"
        G.nodes[new_n]["kind"] = "organization"
    print(f"Relabeled {len(mapping)} fake person nodes to org| nodes.")
    pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
else:
    print("No fake person nodes found.")
