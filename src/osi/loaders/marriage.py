from camoufox.sync_api import Camoufox
import pickle, os, time, re
import networkx as nx

def bypass_tc(page):
    page.goto("https://probate.cuyahogacounty.gov/pa/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1000)
    page.locator("input[type='submit']").first.click()
    page.wait_for_selector("#mpContentPH_txtCaseNum", timeout=15000)

def search_name(page, last, first):
    """Phase 1: Find ML case numbers for a person."""
    page.goto("https://probate.cuyahogacounty.gov/pa/CaseSearch.aspx", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("#mpContentPH_txtLName", timeout=15000)
    
    page.fill("#mpContentPH_txtFName", first)
    page.fill("#mpContentPH_txtLName", last)
    page.select_option("#mpContentPH_ddlCaseCat", value="ML")
    
    page.locator("#mpContentPH_btnSearchByPerson").click()
    page.wait_for_timeout(2500)
    
    text = page.evaluate("() => document.body.innerText")
    # Regex to find modern ML case numbers (e.g., 2017ML42119)
    case_nums = re.findall(r'\b(20\d{2}ML\d+)\b', text)
    return list(set(case_nums))

def search_case(page, case_str):
    """Phase 2: Get the parties for a specific case."""
    year = case_str[:4]
    cat = case_str[4:6]
    num = case_str[6:]
    
    page.goto("https://probate.cuyahogacounty.gov/pa/CaseSearch.aspx", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("#mpContentPH_txtCaseNum", timeout=15000)
    
    # Inject JS to avoid ASP.NET postback wiping the fields
    page.evaluate("""(args) => {
        document.querySelector('#mpContentPH_txtCaseYear').value = args.year;
        document.querySelector('#mpContentPH_txtCaseNum').value = args.num;
        const sel = document.querySelector('#mpContentPH_ddlCaseCat');
        for (let i=0; i<sel.options.length; i++) {
            if (sel.options[i].value === args.cat) { sel.selectedIndex = i; break; }
        }
    }""", {"year": year, "cat": cat, "num": num})
    
    page.wait_for_timeout(500)
    page.locator("#mpContentPH_btnSearchByCase").click()
    page.wait_for_timeout(2500)
    
    # Parse the table rows
    rows = page.evaluate("""() => {
        const trs = document.querySelectorAll('table tr');
        let out = [];
        for (let tr of trs) {
            const tds = tr.querySelectorAll('td');
            if (tds.length >= 4) {
                out.push({
                    name: tds[0].innerText.trim(),
                    role: tds[3].innerText.trim()
                });
            }
        }
        return out;
    }""")
    
    parties = []
    for r in rows:
        # APPLICANT1, APPLICANT2, GROOM, BRIDE
        if r['role'] in ('APPLICANT1', 'APPLICANT2', 'GROOM', 'BRIDE'):
            parties.append(r['name'])
    return parties

def run_pipeline(limit=5):
    print("Loading graph...")
    G = pickle.load(open(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"), "rb"))
    
    # Get some targets that have a voter match
    targets = []
    for n, d in G.nodes(data=True):
        if d.get("voter_match") in ("unique", "address") and n.startswith("owner|") and "," in n:
            parts = n[6:].split(",")
            last = parts[0].strip()
            first = parts[1].strip().split()[0]
            targets.append((n, last, first))
            if len(targets) >= limit:
                break

    with Camoufox(headless=True, i_know_what_im_doing=True) as browser:
        page = browser.new_page()
        bypass_tc(page)
        
        edges_added = 0
        
        for i, (node_key, last, first) in enumerate(targets):
            print(f"\n[{i+1}/{limit}] Processing {last}, {first} ({node_key})...")
            
            try:
                case_nums = search_name(page, last, first)
                if not case_nums:
                    print("  No modern marriage cases found.")
                    continue
                    
                print(f"  Found cases: {case_nums}")
                
                for c in case_nums:
                    time.sleep(2)
                    parties = search_case(page, c)
                    if len(parties) == 2:
                        spouse1, spouse2 = parties
                        print(f"    Case {c}: {spouse1} <-> {spouse2}")
                        
                        # Normalize names to 'LAST, FIRST' format for the graph
                        # e.g., 'DEBORAH GORDON HALL' -> 'HALL, DEBORAH GORDON'
                        def norm(nm):
                            parts = nm.split()
                            if len(parts) > 1:
                                return f"{parts[-1]}, {' '.join(parts[:-1])}"
                            return nm
                            
                        n1 = f"owner|{norm(spouse1)}"
                        n2 = f"owner|{norm(spouse2)}"
                        
                        # Add nodes if they don't exist
                        if n1 not in G:
                            G.add_node(n1, type="owner", kind="person", name=norm(spouse1), source="marriage_record")
                        if n2 not in G:
                            G.add_node(n2, type="owner", kind="person", name=norm(spouse2), source="marriage_record")
                            
                        # Add edge
                        if not G.has_edge(n1, n2):
                            G.add_edge(n1, n2, relation="married_to", source="marriage_record", case_no=c, reliability="A")
                            edges_added += 1
                            
            except Exception as e:
                print(f"  ERROR: {e}")

    if edges_added > 0:
        out_path = os.path.expanduser("~/Desktop/cuyahoga_unified_with_marriages.pkl")
        pickle.dump(G, open(out_path, "wb"))
        print(f"\nSaved graph with {edges_added} new marriage edges to {out_path}")
    else:
        print("\nNo new edges added.")

if __name__ == "__main__":
    run_pipeline(limit=5)
