import pickle, os, re
import networkx as nx

def run():
    G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
    ORG_KEYWORDS = ["CHASE", "GMAC", "AMERICAN G", "AMERICAN GENERAL", "FURNITURE", "SERV.,", "SERV,", "MORT.,", "FINANCE,", "ROKAKIS", "ESQ", "AKA", "ADMINISTRATOR", "DISTRI"]
    mapping = {}
    for n in G.nodes:
        if not n.startswith("owner|"): continue
        name = n[6:]
        upper = name.upper()
        if any(kw in upper for kw in ORG_KEYWORDS):
            mapping[n] = n.replace("owner|", "org|")
            continue
        m = re.match(r"^(JR|SR|III|IV|II)\.?,?\s*(.+)$", name, re.I)
        if m:
            suffix = m.group(1).upper().replace(".", "")
            rest = m.group(2).strip()
            parts = rest.split()
            if len(parts) > 1:
                mapping[n] = "owner|{}, {} {}".format(parts[-1], " ".join(parts[:-1]), suffix)
            continue
        m_flip = re.match(r"^([A-Z])\.?,?\s+([A-Z]+)\s+(JR|SR|III|IV|II)\.?$", name, re.I)
        if m_flip:
            mapping[n] = "owner|{}, {} {}".format(m_flip.group(2).upper(), m_flip.group(1).upper(), m_flip.group(3).upper())
            continue
        if " AKA " in upper:
            parts = name.split(" AKA ")
            mapping[n] = "owner|{}".format(parts[-1])
            
    if mapping:
        G = nx.relabel_nodes(G, mapping)
        for v in mapping.values():
            if v.startswith("org|"):
                G.nodes[v]["type"] = "org"
                G.nodes[v]["kind"] = "organization"
        print("Sweeper relabeled {} nodes.".format(len(mapping)))
        pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
    else:
        print("Sweeper found nothing to clean.")

if __name__ == "__main__":
    run()
