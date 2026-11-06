import pickle, os, json, re

GRAPH_PATH = os.path.expanduser("~/Desktop/cuyahoga_unified.pkl")
MARRIAGE_PATH = os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/data/marriage_progress.jsonl")
COURTS_PATH = os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/data/courts_progress.jsonl")

ENTITY_KEYWORDS = {
    "BANK", "LLC", "INC", "CORP", "ASSN", "ASSOCIATION", "CO", "COMPANY", 
    "COUNTY", "TREASURER", "STATE", "CITY", "OHIO", "TRUST", "CREDIT", 
    "UNION", "FEDERAL", "SAVINGS", "LOAN", "FINANCIAL", "MORTGAGE", 
    "SERVICE", "SERVICES", "GROUP", "PARTNERS", "LP", "LTD", "P.C.", 
    "ESTATE", "PROPERTIES", "REALTY", "ADJUSTMENT", "ENTERPRISES",
    "HOSPITAL", "MEDICAL", "HEALTH", "CENTER", "CLINIC", "PHYSICIANS", 
    "SURGERY", "CARE", "UNIVERSITY", "COLLEGE", "SCHOOL", "AUTHORITY", "TRANSIT", "EDUCATION", "BOARD"
}

def find_or_create_node(G, name_str):
    if not name_str or len(name_str) < 3: return None
    
    upper_str = name_str.upper()
    
    # 1. Check for Entities (Hospitals, Banks, etc.) -> org| node
    if any(kw in upper_str for kw in ENTITY_KEYWORDS):
        key = f"org|{upper_str}"
        if key not in G:
            G.add_node(key, type="org", kind="organization", name=upper_str, source="court_record")
        return key
        
    # 2. Otherwise, treat as Person -> owner| node
    parts = name_str.replace(",", "").split()
    if len(parts) > 1:
        last = parts[-1]
        first = parts[0]
        mid = parts[1][0] if len(parts) > 2 else ""
        norm_name = f"{last}, {first} {mid}".strip().upper()
    else:
        return None

    key = f"owner|{norm_name}"
    if key in G: return key
    
    # Fuzzy match existing owner nodes (strict: must match full last name)
    prefix = f"owner|{last.upper()}, {first.upper()}"
    matches = []
    for n in G.nodes:
        if n.startswith(prefix):
            # Check that the next char is a space or comma (prevents PAGAN -> PAGANO)
            remaining = n[len(prefix):]
            if not remaining or remaining[0] in (" ", ","):
                matches.append(n)
    
    if mid:
        for m in matches:
            if m.upper() == f"owner|{last.upper()}, {first.upper()} {mid.upper()}":
                return m
    else:
        base_nodes = [m for m in matches if m.upper() == f"owner|{last.upper()}, {first.upper()}"]
        if len(base_nodes) == 1:
            return base_nodes[0]
            
    # Create new person node
    G.add_node(key, type="owner", kind="person", name=norm_name, source="court_or_marriage")
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
                        
                        n1 = find_or_create_node(G, p1_name)
                        n2 = find_or_create_node(G, p2_name)
                        
                        if n1 and n2 and n1 != n2:
                            if not G.has_edge(n1, n2):
                                G.add_edge(n1, n2, relation="married_to", source="marriage_record", case_no=case_num, reliability="A")
                                added_marriages += 1
                except Exception:
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
                        # Skip pagination artifacts (names that are just numbers/tabs)
                        if not any(c.isalpha() for c in row.get("name", "")):
                            continue
                        caption = row["caption"]
                        case_num = row["case_num"]
                        
                        # Extract other party
                        other_party = None
                        
                        # Determine if the target is in the caption or just mentioned in the docket
                        node1_last = node1.split(",")[0].replace("owner|", "").strip().lower()
                        parts = node1.replace('owner|', '').split(',')
                        node1_last = parts[0].strip().lower()
                        node1_first = parts[1].strip().split()[0].lower() if len(parts) > 1 else ''
                        in_caption = (node1_last in caption.lower()) and (node1_first in caption.lower())
                        
                        if " v " in caption.lower():
                            parts = caption.lower().split(" v ")
                            if node1_last in parts[0]:
                                other_party = caption.split(" v ")[1] if " v " in caption else None
                            else:
                                other_party = caption.split(" v ")[0] if " v " in caption else None
                        
                        if other_party:
                            # Clean caption suffixes
                            for suffix in [", ET AL", " ET AL", ", ET., AL", " ET., AL", ", ETAL", " ETAL", " ET. AL.", " ET. AL"]:
                                other_party = other_party.replace(suffix, "")
                            other_party = other_party.strip()
                            
                            n2 = find_or_create_node(G, other_party)
                            if n2 and n2 != node1:
                                if not G.has_edge(node1, n2):
                                    # Classify based on case type and caption presence
                                    if case_num.startswith("DR-") and in_caption:
                                        rel = "divorced_from"
                                    elif in_caption:
                                        rel = "litigated_with"
                                    else:
                                        rel = "mentioned_in_case"
                                    
                                    # TEMPORAL BOUNDING: Reject if it happened before they were 18
                                    case_year = int(case_num.split("-")[1])
                                    if case_year < 100:
                                        if case_year < 30:
                                            case_year += 2000
                                        else:
                                            case_year += 1900
                                    dob_str = G.nodes[node1].get("date_of_birth")
                                    if dob_str:
                                        birth_year = int(dob_str.split("-")[0])
                                        if case_year - birth_year < 18:
                                            continue # Skip this edge, they were a child

                                    G.add_edge(node1, n2, relation=rel, source="court_record", case_no=case_num, caption=row["caption"], reliability="A")
                                    added_courts += 1
                except Exception:
                    pass

    print(f"\nAdded {added_marriages} marriage edges.")
    print(f"Added {added_courts} court edges.")
    print(f"Graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
    
    pickle.dump(G, open(GRAPH_PATH, "wb"))
    print(f"Saved to {GRAPH_PATH}")

if __name__ == "__main__":
    main()
