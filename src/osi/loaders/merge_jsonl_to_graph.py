import pickle, os, json, re

GRAPH_PATH = os.path.expanduser("~/Desktop/cuyahoga_unified.pkl")
MARRIAGE_PATH = os.path.expanduser("~/Desktop/marriage_progress.jsonl")
COURTS_PATH = os.path.expanduser("~/Desktop/courts_progress.jsonl")

# Entity filter to prevent creating nodes for banks, LLCs, and government titles
ENTITY_KEYWORDS = {
    "BANK", "LLC", "INC", "CORP", "ASSN", "ASSOCIATION", "CO", "COMPANY", 
    "COUNTY", "TREASURER", "STATE", "CITY", "OHIO", "TRUST", "CREDIT", 
    "UNION", "FEDERAL", "SAVINGS", "LOAN", "FINANCIAL", "MORTGAGE", 
    "SERVICE", "SERVICES", "GROUP", "PARTNERS", "LP", "LTD", "P.C.", 
    "ESTATE", "PROPERTIES", "REALTY", "ADJUSTMENT", "ENTERPRISES"
}

def is_valid_person(name_str):
    if not name_str or len(name_str) < 3: return False
    upper_str = name_str.upper()
    if any(kw in upper_str for kw in ENTITY_KEYWORDS):
        return False
    return True

def find_or_create_person(G, name_str):
    if not is_valid_person(name_str):
        return None
    
    # Normalize "FIRST LAST" to "LAST, FIRST"
    parts = name_str.replace(",", "").split()
    if len(parts) > 1:
        last = parts[-1]
        first = parts[0]
        norm_name = f"{last}, {' '.join(parts[:-1])}"
    else:
        return None

    key = f"owner|{norm_name.upper()}"
    if key in G: return key
    
    # Try fuzzy match against existing nodes
    if last and first:
        prefix = f"owner|{last.upper()}, {first.upper()}"
        for n in G.nodes:
            if n.startswith(prefix): return n
            
    # Create new node
    G.add_node(key, type="owner", kind="person", name=norm_name.upper(), source="court_or_marriage")
    return key

def main():
    print("Loading graph...")
    G = pickle.load(open(GRAPH_PATH, "rb"))
    before_edges = G.number_of_edges()
    
    added_marriages = 0
    added_courts = 0
    
    # 1. Process Marriages
    if os.path.exists(MARRIAGE_PATH):
        print(f"Processing {MARRIAGE_PATH}...")
        with open(MARRIAGE_PATH) as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("status") != "success": continue
                    node1 = data["node_key"]
                    for party_data in data.get("parties", []):
                        case_num = party_data["case"]
                        p1_name, p2_name = party_data["parties"]
                        
                        n1 = find_or_create_person(G, p1_name)
                        n2 = find_or_create_person(G, p2_name)
                        
                        if n1 and n2 and n1 != n2:
                            if not G.has_edge(n1, n2):
                                G.add_edge(n1, n2, relation="married_to", source="marriage_record", case_no=case_num, reliability="A")
                                added_marriages += 1
                except Exception as e:
                    pass

    # 2. Process Courts
    if os.path.exists(COURTS_PATH):
        print(f"Processing {COURTS_PATH}...")
        with open(COURTS_PATH) as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("status") != "success": continue
                    node1 = data["node_key"]
                    for row in data.get("rows", []):
                        caption = row["caption"]
                        case_num = row["case_num"]
                        
                        # Extract other party
                        other_party = None
                        if " v " in caption.lower():
                            parts = caption.lower().split(" v ")
                            if node1[6:].lower() in parts[0]:
                                other_party = caption.split(" v ")[1] if " v " in caption else None
                            else:
                                other_party = caption.split(" v ")[0] if " v " in caption else None
                        
                        if other_party:
                            # Clean caption suffixes
                            for suffix in [", ET AL", " ET AL", ", ET., AL", " ET., AL", ", ETAL", " ETAL"]:
                                other_party = other_party.replace(suffix, "")
                            other_party = other_party.strip()
                            
                            n2 = find_or_create_person(G, other_party)
                            if n2 and n2 != node1:
                                if not G.has_edge(node1, n2):
                                    G.add_edge(node1, n2, relation="litigated_with", source="court_record", case_no=case_num, caption=row["caption"], reliability="A")
                                    added_courts += 1
                except Exception as e:
                    pass

    print(f"\nAdded {added_marriages} marriage edges.")
    print(f"Added {added_courts} court edges.")
    print(f"Graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
    
    pickle.dump(G, open(GRAPH_PATH, "wb"))
    print(f"Saved to {GRAPH_PATH}")

if __name__ == "__main__":
    main()
