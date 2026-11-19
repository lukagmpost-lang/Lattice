from pathlib import Path

p = Path("src/osi/static/index.html")
text = p.read_text(encoding="utf-8")

if '<select id="popular-subreddit-select"' in text:
    print("Dropdown HTML already exists.")
    raise SystemExit(0)

# Find the upload button label
upload_html = '<input type="file" id="file-input" style="display:none">'
if upload_html in text:
    idx = text.find(upload_html)
    end_idx = text.find('</label>', idx)
    
    if end_idx != -1:
        dropdown_html = '''
  <div style="display:flex; gap:8px; align-items:center; margin-left: 10px;">
    <select id="popular-subreddit-select" style="padding:8px 12px; border:1px solid var(--line); font-family:inherit; font-size:13px; min-width:200px;">
      <option value="">Loading popular subreddits...</option>
    </select>
    <button class="os-btn" id="reddit-btn" type="button">Load Subreddit</button>
  </div>'''
        text = text[:end_idx+8] + dropdown_html + text[end_idx+8:]
        p.write_text(text, encoding="utf-8")
        print("Success: Injected HTML dropdown.")
    else:
        print("ERROR: Could not find closing </label>.")
else:
    print("ERROR: Could not find file-input element.")
