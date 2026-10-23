from pathlib import Path
import re

# 1. Fix the UI Layout (Split into two clean rows)
p_html = Path("src/osi/static/index.html")
html = p_html.read_text(encoding="utf-8")

new_controls = '''<section class="controls">
  <label for="run-selector">Run</label>
  <select id="run-selector"><option value="">loading...</option></select>
  
  <label class="os-btn">
    Upload chat
    <input type="file" id="file-input" style="display:none">
  </label>
</section>

<section class="controls" style="border-top: none; padding-top: 0;">
  <label for="popular-subreddit-select">Or Load Subreddit</label>
  <select id="popular-subreddit-select" style="padding:8px 12px; border:1px solid var(--line); font-family:inherit; font-size:13px; min-width:220px;">
    <option value="">Loading subreddits...</option>
  </select>
  <button class="os-btn" id="reddit-btn" type="button">Load Subreddit</button>
</section>'''

html = re.sub(r'<section class="controls">.*?</section>', new_controls, html, flags=re.DOTALL)

# Show exact backend error instead of generic alert
html = html.replace("alert('Failed to load subreddit');", "const err = await resp.json(); alert('Error: ' + (err.detail || 'Unknown error'));")
p_html.write_text(html, encoding="utf-8")
print("Fixed UI layout and error handling.")

# 2. Fix the Reddit Loader (Add User-Agent header)
p_reddit = Path("src/osi/loaders/reddit.py")
reddit = p_reddit.read_text(encoding="utf-8")

if 'headers = {"User-Agent"' not in reddit:
    reddit = reddit.replace(
        'resp = requests.get(url, params=params, timeout=30)',
        'headers = {"User-Agent": "Lattice/1.0 (Academic Research)"}\n    resp = requests.get(url, params=params, headers=headers, timeout=30)'
    )
    p_reddit.write_text(reddit, encoding="utf-8")
    print("Added User-Agent to Reddit loader.")
