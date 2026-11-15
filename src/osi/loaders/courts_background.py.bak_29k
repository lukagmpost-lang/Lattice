from camoufox.sync_api import Camoufox
import os, time, json

TARGETS_PATH = os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/data/scrape_targets_full.json")
PROGRESS_PATH = os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/data/courts_progress.jsonl")

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

def main():
    targets = load_targets()
    print(f"Remaining court targets: {len(targets)}", flush=True)

    with Camoufox(headless=True, i_know_what_im_doing=True) as browser:
        page = browser.new_page()
        
        for i, t in enumerate(targets):
            try:
                page.goto("https://cpdocket.cp.cuyahogacounty.us/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1000)
                if page.locator("#SheetContentPlaceHolder_btnYes").count() > 0:
                    page.locator("#SheetContentPlaceHolder_btnYes").click()
                    page.wait_for_timeout(1500)
                
                page.locator("#SheetContentPlaceHolder_rbCivilName").click()
                page.wait_for_timeout(1500)
                page.fill("#SheetContentPlaceHolder_civilNameSearch_txtLastName", t["last"])
                page.fill("#SheetContentPlaceHolder_civilNameSearch_txtFirstName", t["first"])
                page.locator("#SheetContentPlaceHolder_civilNameSearch_btnSubmitName").click()
                page.wait_for_timeout(3000)
                
                rows = page.evaluate("""() => {
                    const trs = document.querySelectorAll('table tr'); let out = [];
                    for (let tr of trs) {
                        const tds = tr.querySelectorAll('td');
                        if (tds.length >= 5) out.push({name: tds[0].innerText.trim(), role: tds[2].innerText.trim(), case_num: tds[3].innerText.trim(), caption: tds[4].innerText.trim()});
                    }
                    return out;
                }""")
                
                with open(PROGRESS_PATH, "a") as f:
                    f.write(json.dumps({"node_key": t["node_key"], "status": "success", "rows": rows}) + "\n")
                    
                if i % 5 == 0:
                    print(f"Progress: {i}/{len(targets)}", flush=True)
            except Exception as e:
                with open(PROGRESS_PATH, "a") as f:
                    f.write(json.dumps({"node_key": t["node_key"], "status": "error", "msg": str(e)}) + "\n")
            time.sleep(3)

if __name__ == "__main__":
    main()
