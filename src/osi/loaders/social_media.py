"""
Extract and run OsintHunter's 23 platform handlers.
We use the handler functions directly to check if our Top Brokers have
public accounts on Keybase, GitHub, Reddit, etc.
"""
import sys
import os
import asyncio

# Add the OsintHunter directory to sys.path so we can import its modules
sys.path.insert(0, os.path.expanduser("~/Desktop/OsintHunter"))

try:
    from app.modules.username import (
        p_github, p_keybase, p_hackernews, p_bluesky, 
        p_reddit, p_devto, p_dockerhub, p_stackoverflow, p_lobsters
    )
    print("SUCCESS: Imported OsintHunter handlers.")
except ImportError as e:
    print(f"FAILED to import OsintHunter handlers: {e}")
    sys.exit(1)

# A simplified ctx class to satisfy the handlers' expected interface
class SimpleCtx:
    def __init__(self):
        import httpx
        self.http = httpx.AsyncClient(timeout=15, follow_redirects=True)
        self.value = ""
    
    async def get_json(self, url, headers=None, params=None):
        try:
            r = await self.http.get(url, headers=headers, params=params)
            return r.status_code, r.json() if r.status_code == 200 else None
        except Exception:
            return 500, None
    
    def key(self, name):
        return None # No API keys for this test

async def check_username(username):
    ctx = SimpleCtx()
    ctx.value = username
    platforms = [
        ("GitHub", p_github), ("Keybase", p_keybase), ("HackerNews", p_hackernews),
        ("Bluesky", p_bluesky), ("Reddit", p_reddit), ("Dev.to", p_devto),
        ("DockerHub", p_dockerhub), ("StackOverflow", p_stackoverflow), ("Lobsters", p_lobsters)
    ]
    
    results = []
    for name, handler in platforms:
        try:
            res = await handler(ctx, username)
            if res:
                results.append({"platform": name, "url": res.get("url"), "name": res.get("name")})
        except Exception as e:
            pass # Silently ignore handler errors
    await ctx.http.aclose()
    return results

if __name__ == "__main__":
    # Test on a broker name (stripped of punctuation and spaces for a username guess)
    test_name = "johnabbott"
    print(f"Checking platforms for alias: {test_name}...")
    found = asyncio.run(check_username(test_name))
    
    if found:
        for f in found:
            print(f"  Found on {f['platform']}: {f['url']} (Name: {f['name']})")
    else:
        print("  No accounts found on the 9 platforms checked.")
