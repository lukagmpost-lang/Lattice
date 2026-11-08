from camoufox.sync_api import Camoufox

import os
import sys
import json
from datetime import datetime

BANDWIDTH_FILE = os.path.expanduser("~/Desktop/OSI/Open-Source-Intelligence/data/bandwidth_today.json")
BANDWIDTH_LIMIT_BYTES = 15 * 1024 * 1024 * 1024  # 15 GB

def load_bandwidth():
    try:
        with open(BANDWIDTH_FILE) as f:
            data = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        if data.get("date") != today:
            return {"date": today, "bytes": 0}
        return data
    except Exception:
        return {"date": datetime.now().strftime("%Y-%m-%d"), "bytes": 0}

def save_bandwidth(bw):
    try:
        with open(BANDWIDTH_FILE, "w") as f:
            json.dump(bw, f)
    except Exception:
        pass

def check_bandwidth_limit(bw):
    if bw["bytes"] >= BANDWIDTH_LIMIT_BYTES:
        used_gb = bw["bytes"] / (1024**3)
        print(f"\n[BANDWIDTH LIMIT] {used_gb:.2f} GB of 15 GB used. Stopping scraper.")
        save_bandwidth(bw)
        sys.exit(0)


import os, time, json

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

    with Camoufox(headless=True, i_know_what_im_doing=True, firefox_user_prefs=FIREFOX_PREFS) as browser:
        page = browser.new_page()
        bw = load_bandwidth()

        def track_response(response):
            try:
                cl = response.headers.get("content-length")
                if cl:
                    bw["bytes"] += int(cl)
            except Exception:
                pass

        page.on("response", track_response)
        
        # BLOCK IMAGES AND CSS TO SAVE BANDWIDTH (Reduces usage by 90%)
        def block_assets(route):
            if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
                route.abort()
            else:
                route.continue_()
        page.route("**/*", block_assets)
        
        for i, t in enumerate(targets):
            check_bandwidth_limit(bw)
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
            save_bandwidth(bw)
            time.sleep(15)

if __name__ == "__main__":
    main()
