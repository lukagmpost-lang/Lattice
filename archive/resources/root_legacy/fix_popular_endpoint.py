from pathlib import Path
import re

p = Path("src/osi/server.py")
text = p.read_text(encoding="utf-8")

new_endpoint = '''@app.get("/api/reddit/popular")
def api_reddit_popular() -> list[dict]:
    """Return a curated list of the most popular subreddits."""
    # Since Arctic Shift doesn't have a global "sort by subscribers" endpoint,
    # we provide a hardcoded list of the biggest subreddits to populate the UI.
    return [
        {"name": "AskReddit", "subscribers": 45000000},
        {"name": "funny", "subscribers": 40000000},
        {"name": "pics", "subscribers": 30000000},
        {"name": "gaming", "subscribers": 40000000},
        {"name": "worldnews", "subscribers": 35000000},
        {"name": "aww", "subscribers": 35000000},
        {"name": "movies", "subscribers": 32000000},
        {"name": "science", "subscribers": 28000000},
        {"name": "todayilearned", "subscribers": 30000000},
        {"name": "python", "subscribers": 1200000},
        {"name": "csuohio", "subscribers": 5000}
    ]
'''

# Replace the existing function with the static one
text = re.sub(r'@app\.get\("/api/reddit/popular"\)\ndef api_reddit_popular.*?return \[.*?\]\n', new_endpoint, text, flags=re.DOTALL)
p.write_text(text, encoding="utf-8")
print("Fixed: Replaced /api/reddit/popular with a static list.")
