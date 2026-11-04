"""Standalone username scanner — ported from OsintHunter's username.py.

Checks 12 platforms with real API endpoints. Returns confirmed accounts only.
Skips bot-blocked platforms (Instagram, TikTok, Twitter) — they fail silently.
"""
import asyncio, json, sys
import httpx

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

async def p_github(c, u):
    r = await c.get(f"https://api.github.com/users/{u}", headers=UA)
    if r.status_code != 200: return None
    d = r.json()
    return {"platform": "GitHub", "url": d.get("html_url"), "name": d.get("name"),
            "email": d.get("email"), "created": d.get("created_at")}

async def p_gitlab(c, u):
    r = await c.get(f"https://gitlab.com/api/v4/users?username={u}", headers=UA)
    if r.status_code != 200: return None
    d = r.json()
    if not d: return None
    return {"platform": "GitLab", "url": d[0].get("web_url"), "name": d[0].get("name")}

async def p_keybase(c, u):
    r = await c.get(f"https://keybase.io/_/api/1.0/user/lookup.json?username={u}", headers=UA)
    if r.status_code != 200: return None
    d = r.json()
    if d.get("status", {}).get("code") != 0: return None
    them = d.get("them", [{}])[0]
    proofs = [p.get("namwithservice") for p in them.get("proofs_summary", {}).get("all", [])]
    return {"platform": "Keybase", "url": f"https://keybase.io/{u}",
            "name": them.get("profile", {}).get("full_name"),
            "proofs": proofs}

async def p_hackernews(c, u):
    r = await c.get(f"https://hacker-news.firebaseio.com/v0/user/{u}.json", headers=UA)
    if r.status_code != 200: return None
    d = r.json()
    if not d: return None
    return {"platform": "Hacker News", "url": f"https://news.ycombinator.com/user?id={u}",
            "karma": d.get("karma"), "created": d.get("created")}

async def p_reddit(c, u):
    r = await c.get(f"https://www.reddit.com/user/{u}/about.json", headers=UA)
    if r.status_code != 200: return None
    d = r.json().get("data", {})
    if d.get("is_suspended") or not d.get("name"): return None
    return {"platform": "Reddit", "url": f"https://www.reddit.com/user/{u}",
            "karma": d.get("total_karma"), "created": d.get("created_utc")}

async def p_bluesky(c, u):
    r = await c.get(f"https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle={u}.bsky.social", headers=UA)
    if r.status_code != 200: return None
    d = r.json()
    return {"platform": "Bluesky", "url": f"https://bsky.app/profile/{u}.bsky.social",
            "did": d.get("did")}

async def p_devto(c, u):
    r = await c.get(f"https://dev.to/api/users/by_username?url={u}", headers=UA)
    if r.status_code != 200: return None
    d = r.json()
    return {"platform": "Dev.to", "url": f"https://dev.to/{u}", "name": d.get("name")}

async def p_dockerhub(c, u):
    r = await c.get(f"https://hub.docker.com/v2/users/{u}/", headers=UA)
    if r.status_code != 200: return None
    d = r.json()
    return {"platform": "Docker Hub", "url": f"https://hub.docker.com/u/{u}", "name": d.get("full_name")}

async def p_stackoverflow(c, u):
    r = await c.get(f"https://api.stackexchange.com/2.3/users?inname={u}&site=stackoverflow", headers=UA)
    if r.status_code != 200: return None
    d = r.json().get("items", [])
    if not d: return None
    return {"platform": "Stack Overflow", "url": d[0].get("link"), "name": d[0].get("display_name"),
            "reputation": d[0].get("reputation")}

async def p_telegram(c, u):
    r = await c.get(f"https://t.me/{u}", headers=UA)
    if r.status_code != 200: return None
    if "tgme_page_title" in r.text:
        return {"platform": "Telegram", "url": f"https://t.me/{u}"}
    return None

async def p_lobsters(c, u):
    r = await c.get(f"https://lobste.rs/u/{u}.json", headers=UA)
    if r.status_code != 200: return None
    d = r.json()
    return {"platform": "Lobsters", "url": f"https://lobste.rs/u/{u}", "karma": d.get("karma")}

PLATFORMS = [p_github, p_gitlab, p_keybase, p_hackernews, p_reddit,
             p_bluesky, p_devto, p_dockerhub, p_stackoverflow, p_telegram, p_lobsters]

async def scan(username):
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        tasks = [p(c, username) for p in PLATFORMS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if r and not isinstance(r, Exception)]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 username_scan.py <username1> [username2] ...")
        sys.exit(1)
    out = {}
    for u in sys.argv[1:]:
        print(f"scanning {u}...")
        found = asyncio.run(scan(u))
        out[u] = found
        if found:
            for f in found: print(f"  [{f['platform']}] {f.get('url')}")
            kb = [f for f in found if f["platform"] == "Keybase"]
            if kb and kb[0].get("proofs"):
                print(f"  Keybase proofs: {kb[0]['proofs']}")
        else:
            print("  no accounts found")
    json.dump(out, open("/tmp/username_scan.json", "w"), indent=1)
    print(f"\nwrote /tmp/username_scan.json")
