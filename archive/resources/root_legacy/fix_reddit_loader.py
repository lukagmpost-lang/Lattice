from pathlib import Path

# Update server.py to print the exact traceback
p = Path("src/osi/server.py")
text = p.read_text(encoding="utf-8")
if "traceback.print_exc()" not in text:
    text = text.replace(
        'graph, meta = load_subreddit(subreddit, limit=limit)',
        'import traceback\n        try:\n            graph, meta = load_subreddit(subreddit, limit=limit)\n        except Exception as e:\n            traceback.print_exc()\n            raise'
    )
    p.write_text(text, encoding="utf-8")
    print("Patched server.py to show exact Python errors.")

# Update index.html to safely handle HTML error responses
p2 = Path("src/osi/static/index.html")
html = p2.read_text(encoding="utf-8")
old_catch = "const err = await resp.json(); alert('Error: ' + (err.detail || 'Unknown error'));"
new_catch = "let msg = 'Failed to load. Server returned ' + resp.status; try { const err = await resp.json(); if (err.detail) msg = err.detail; } catch(e) {} alert(msg);"
if old_catch in html:
    html = html.replace(old_catch, new_catch)
    p2.write_text(html, encoding="utf-8")
    print("Patched HTML to handle HTML error pages.")
