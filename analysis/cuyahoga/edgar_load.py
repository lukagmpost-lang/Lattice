import json, os, pickle, re, time, urllib.request, urllib.error

UA = {"User-Agent": "OSI Research research@cuyahoga-graph.org"}
CIKS = {"PULTE": "0000822416", "NVR": "0000906163"}

def get(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = 2 ** attempt
                print(f"    {e.code}, retry in {wait}s")
                time.sleep(wait)
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt); continue
            raise
    return ""

G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
added_people = added_edges = 0
seen = set()

for brand, cik in CIKS.items():
    print(f"\n=== {brand} (CIK {cik}) ===")
    idx = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    forms = idx["filings"]["recent"]
    form4s = []
    for i in range(len(forms["form"])):
        if forms["form"][i] == "4":
            acc = forms["accessionNumber"][i].replace("-", "")
            doc = forms["primaryDocument"][i]
            raw = doc.split("/")[-1]
            form4s.append((acc, raw))
    print(f"  {len(form4s)} Form 4 filings; using raw XML path")
    for acc, doc in form4s[:40]:
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
        try:
            xml = get(url)
        except Exception as e:
            print(f"    skip {acc}: {e}"); continue
        if "<ownershipDocument" not in xml:
            continue
        for m in re.finditer(
            r"<rptOwnerName>([^<]+)</rptOwnerName>.*?"
            r"<officerTitle>([^<]*)</officerTitle>",
            xml, re.S):
            name = m.group(1).strip().upper()
            title = m.group(2).strip() or "Officer"
            key = (brand, name)
            if not name or key in seen: continue
            seen.add(key)
            pk = f"person|{name}"
            ent = f"entity|SEC:{brand}"
            if ent not in G:
                G.add_node(ent, type="entity", name=brand,
                           cik=cik, source="sec_edgar")
            if pk not in G:
                G.add_node(pk, type="person", name=name, source="sec_edgar")
                added_people += 1
            if not G.has_edge(pk, ent):
                G.add_edge(pk, ent, relation="officer_of",
                           title=title, source="sec_edgar")
                added_edges += 1
        time.sleep(0.15)

for sec_n in [n for n in G.nodes if n.startswith("entity|SEC:")]:
    brand = G.nodes[sec_n].get("name","")
    for owner_n in list(G.nodes):
        if owner_n.startswith("owner|") and brand in owner_n.upper():
            if not G.has_edge(owner_n, sec_n):
                G.add_edge(owner_n, sec_n, relation="registered_as", source="sec_edgar")

pickle.dump(G, open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "wb"))
print(f"\npeople added: {added_people}, officer_of edges: {added_edges}")
print(f"graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
print(f"person nodes: {sum(1 for _,d in G.nodes(data=True) if d.get('type')=='person')}")
