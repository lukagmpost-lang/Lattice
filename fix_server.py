from pathlib import Path

p = Path("src/osi/server.py")
text = p.read_text(encoding="utf-8")

start_marker = '@app.get("/api/reddit/popular")'
end_marker = 'def main() -> None:'

start_idx = text.find(start_marker)
end_idx = text.find(end_marker)

if start_idx != -1 and end_idx != -1:
    clean_func = '''@app.get("/api/reddit/popular")
def api_reddit_popular() -> list[dict]:
    """Return a curated list of the most popular subreddits."""
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
    text = text[:start_idx] + clean_func + text[end_idx:]
    p.write_text(text, encoding="utf-8")
    print("Success: Repaired the broken function in server.py.")
else:
    print("ERROR: Could not find the markers to fix the file.")
