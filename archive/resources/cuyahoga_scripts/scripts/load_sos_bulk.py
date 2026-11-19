import csv, glob, os, pickle, re
from collections import Counter

def _u(s): return "" if s is None else re.sub(r"\s+"," ",str(s)).strip().upper()

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))

owner_index = {}
for n in G.nodes:
    if n.startswith("owner|"):
        owner_index[_u(n[6:])] = n

files = sorted(glob.glob(os.path.expanduser("~/Downloads/WI*.TXT")))
print(f"files: {len(files)}")

rows_total = 0
matched_entities = 0
added_agent_edges = 0
added_assoc_edges = 0
added_agent_nodes = 0
added_mail_nodes = 0
commercial_agents = Counter()

for path in files:
    with open(path, newline="", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows_total += 1
            bname = _u(row.get("BUSINESS NAME"))
            if not bname: continue
            owner_key = owner_index.get(bname)
            if not owner_key: continue
            matched_entities += 1
            agent = _u(row.get("AGENT ADDRESS NAME"))
            if agent:
                commercial_agents[agent] += 1
                ak = f"owner|{agent}"
                if ak not in G:
                    kind = "entity" if any(k in agent for k in ("LLC", "INC", "SERVICE", "CORP")) else "person"
                    G.add_node(ak, type="owner", kind=kind, name=agent, source="ohio_sos_bulk")
                    added_agent_nodes += 1
                if not G.has_edge(ak, owner_key):
                    G.add_edge(ak, owner_key, relation="statutory_agent_of", source="ohio_sos_bulk")
                    added_agent_edges += 1
            assoc = _u(row.get("BUSINESS ASSOCIATE NAMES"))
            if assoc and assoc != agent:
                bk = f"owner|{assoc}"
                if bk not in G:
                    G.add_node(bk, type="owner", kind="person", name=assoc, source="ohio_sos_bulk")
                    added_agent_nodes += 1
                if not G.has_edge(bk, owner_key):
                    G.add_edge(bk, owner_key, relation="associated_with", source="ohio_sos_bulk")
                    added_assoc_edges += 1
            addr1 = _u(row.get("AGENT ADDRESS 1"))
            if addr1 and agent:
                azip = _u(row.get("AGENT ZIP"))
                mk = f"mail|{addr1}|{azip}"
                if mk not in G:
                    G.add_node(mk, type="address", street=addr1, zip=azip, source="ohio_sos_bulk")
                    added_mail_nodes += 1
                ak = f"owner|{agent}"
                if ak in G and not G.has_edge(ak, mk):
                    G.add_edge(ak, mk, relation="owns_from", source="ohio_sos_bulk")

pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
print(f"rows read: {rows_total:,}")
print(f"matched existing owner nodes: {matched_entities:,}")
print(f"agent nodes added: {added_agent_nodes}")
print(f"statutory_agent_of edges: {added_agent_edges}")
print(f"associated_with edges: {added_assoc_edges}")
print(f"agent mail nodes added: {added_mail_nodes}")
print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
print("\ntop 10 commercial agents by match count:")
for name, n in commercial_agents.most_common(10):
    print(f"  {n:4d}  {name[:60]}")
