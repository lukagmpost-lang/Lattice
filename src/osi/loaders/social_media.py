import sys, os, asyncio
sys.path.insert(0, os.path.expanduser("~/Desktop/OsintHunter"))
from app.modules.username import (
    p_github, p_keybase, p_hackernews, p_bluesky, 
    p_reddit, p_devto, p_dockerhub, p_stackoverflow, p_lobsters
)

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
        return None

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
                attrs = res.get("attrs", {})
                results.append({
                    "platform": name,
                    "url": res.get("url"),
                    "real_name": attrs.get("Nombre") or res.get("name") or "",
                    "location": res.get("location") or "",
                    "bio": attrs.get("Bio") or res.get("bio") or ""
                })
        except Exception:
            pass
    await ctx.http.aclose()
    return results
