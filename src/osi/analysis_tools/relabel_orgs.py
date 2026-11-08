import pickle, os
import networkx as nx

def run():
    G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
    KEYWORDS = {
        "BANK", "LLC", "INC", "CORP", "ASSN", "ASSOCIATION", "CO", "COMPANY", 
        "COUNTY", "TREASURER", "STATE", "CITY", "OHIO", "TRUST", "CREDIT", 
        "UNION", "FEDERAL", "SAVINGS", "LOAN", "FINANCIAL", "MORTGAGE", 
        "SERVICE", "SERVICES", "GROUP", "PARTNERS", "LP", "LTD", "P.C.", 
        "ESTATE", "PROPERTIES", "REALTY", "ADJUSTMENT", "ENTERPRISES",
        "HOSPITAL", "MEDICAL", "HEALTH", "CENTER", "CLINIC", "PHYSICIANS", 
        "SURGERY", "CARE", "UNIVERSITY", "COLLEGE", "SCHOOL", "AUTHORITY", 
        "TRANSIT", "EDUCATION", "BOARD", "CAPITAL", "N.A.", "NA,"
    }
    mapping = {}
    for n in G.nodes:
        if n.startswith("owner|"):
            upper = n.upper()
            if any(kw in upper for kw in KEYWORDS):
                mapping[n] = n.replace("owner|", "org|")
                
    if mapping:
        G = nx.relabel_nodes(G, mapping)
        for v in mapping.values():
            G.nodes[v]["type"] = "org"
            G.nodes[v]["kind"] = "organization"
        print(f"Relabeled {len(mapping)} org nodes.")
        pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
    else:
        print("No orgs found to relabel.")

if __name__ == "__main__":
    run()
