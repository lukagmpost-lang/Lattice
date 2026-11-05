from camoufox.sync_api import Camoufox
import os, time, json, re

FIREFOX_PREFS = {
    "network.trr.mode": 5,              # disable DoH, use system resolver
    "network.http.http3.enabled": False,
    "network.http.altsvc.enabled": False,
    "network.http.altsvc.oe": False,
    "network.http.http2.enabled": False,
    "security.OCSP.enabled": 0,
    "security.OCSP.require": False,
}

TARGETS_PATH = os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/data/scrape_targets_29k.json")
PROGRESS_PATH = os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/data/marriage_progress.jsonl")

def load_targets():
    targets = json.load(open(TARGETS_PATH))
    processed = set()
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH) as f:
            for line in f:
                try:
                    _r = json.loads(line)
                    if _r.get("status") in ("success", "no_cases"):
                        processed.add(_r["node_key"])
                except: pass
    return [t for t in targets if t["node_key"] not in processed]

def bypass_tc(page):
    page.goto("https://probate.cuyahogacounty.gov/pa/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)
    
    # Try to click the TOS button if it exists
    try:
        btn = page.locator("input[type='submit']").first
        if btn.is_visible(timeout=3000):
            btn.click()
    except Exception:
        pass # If no button, maybe TOS is already accepted
        
    # Wait for the search form
    try:
        page.wait_for_selector("#mpContentPH_txtCaseNum", timeout=15000)
    except Exception:
        pass # If it fails, the search function will handle it

def search_name(page, last, first):
    page.goto("https://probate.cuyahogacounty.gov/pa/CaseSearch.aspx", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("#mpContentPH_txtLName", timeout=15000)
    page.fill("#mpContentPH_txtFName", first)
    page.fill("#mpContentPH_txtLName", last)
    page.select_option("#mpContentPH_ddlCaseCat", value="ML")
    page.locator("#mpContentPH_btnSearchByPerson").click()
    page.wait_for_timeout(2500)
    text = page.evaluate("() => document.body.innerText")
    return list(set(re.findall(r'\b(20\d{2}ML\d+)\b', text)))

def search_case(page, case_str):
    year, cat, num = case_str[:4], case_str[4:6], case_str[6:]
    page.goto("https://probate.cuyahogacounty.gov/pa/CaseSearch.aspx", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("#mpContentPH_txtCaseNum", timeout=15000)
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
    rows = page.evaluate("""() => {
        const trs = document.querySelectorAll('table tr'); let out = [];
        for (let tr of trs) {
            const tds = tr.querySelectorAll('td');
            if (tds.length >= 4) out.push({name: tds[0].innerText.trim(), role: tds[3].innerText.trim()});
        }
        return out;
    }""")
    return [r['name'] for r in rows if r['role'] in ('APPLICANT1', 'APPLICANT2', 'GROOM', 'BRIDE')]

def main():
    targets = load_targets()
    print(f"Remaining targets: {len(targets)}", flush=True)

    with Camoufox(headless=True, i_know_what_im_doing=True, firefox_user_prefs=FIREFOX_PREFS) as browser:
        page = browser.new_page()
        bypass_tc(page)
        
        for i, t in enumerate(targets):
            try:
                case_nums = search_name(page, t["last"], t["first"])
                parties = []
                if case_nums:
                    for c in case_nums:
                        time.sleep(2)
                        p = search_case(page, c)
                        if len(p) == 2:
                            parties.append({"case": c, "parties": p})
                
                with open(PROGRESS_PATH, "a") as f:
                    f.write(json.dumps({"node_key": t["node_key"], "status": "success", "parties": parties}) + "\n")
                    
                if i % 5 == 0:
                    print(f"Progress: {i}/{len(targets)}", flush=True)
            except Exception as e:
                with open(PROGRESS_PATH, "a") as f:
                    f.write(json.dumps({"node_key": t["node_key"], "status": "error", "msg": str(e)}) + "\n")

if __name__ == "__main__":
    main()
