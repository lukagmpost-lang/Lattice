from pathlib import Path

p = Path("/Users/2950639/Desktop/OSI/Open-Source-Intelligence/src/osi/static/index.html")
text = p.read_text(encoding="utf-8")

if "popular-subreddit-select" in text:
    print("UI already updated.")
    raise SystemExit(0)

# Replace the text input with a dropdown
old_input = '''  <div style="display:flex; gap:8px; align-items:center;">
    <input type="text" id="reddit-input" placeholder="e.g. python" style="padding:8px 12px; border:1px solid var(--line); font-family:inherit; font-size:13px; width:150px;">
    <button class="os-btn" id="reddit-btn" type="button">Load Subreddit</button>
  </div>'''

new_input = '''  <div style="display:flex; gap:8px; align-items:center;">
    <select id="popular-subreddit-select" style="padding:8px 12px; border:1px solid var(--line); font-family:inherit; font-size:13px; min-width:200px;">
      <option value="">Loading popular subreddits...</option>
    </select>
    <button class="os-btn" id="reddit-btn" type="button">Load Subreddit</button>
  </div>'''

if old_input in text:
    text = text.replace(old_input, new_input, 1)
    print("Replaced text input with dropdown.")

# Update the JS to populate the dropdown and handle the selection
old_js = '''  function setupReddit() {
    const btn = document.getElementById('reddit-btn');
    const input = document.getElementById('reddit-input');
    if (!btn || !input) return;
    
    btn.addEventListener('click', async () => {
      const sub = input.value.trim();
      if (!sub) return;
      
      btn.disabled = true;
      btn.textContent = 'Loading...';
      try {
        const resp = await fetch('/api/reddit', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({subreddit: sub, limit: 500})
        });
        if (resp.ok) {
          const data = await resp.json();
          await loadRuns();
          document.getElementById('run-selector').value = data.run;
          await selectRun(data.run);
          input.value = '';
        } else {
          alert('Failed to load subreddit');
        }
      } catch (e) {
        alert('Error: ' + e.message);
      } finally {
        btn.disabled = false;
        btn.textContent = 'Load Subreddit';
      }
    });
  }'''

new_js = '''  async function loadPopularSubreddits() {
    const select = document.getElementById('popular-subreddit-select');
    if (!select) return;
    try {
      const resp = await fetch('/api/reddit/popular');
      const data = await resp.json();
      select.innerHTML = '<option value="">Choose a subreddit...</option>';
      for (const sub of data) {
        const opt = document.createElement('option');
        opt.value = sub.name;
        const count = sub.subscribers ? `${(sub.subscribers / 1000000).toFixed(1)}M` : '?';
        opt.textContent = `r/${sub.name} (${count} members)`;
        select.appendChild(opt);
      }
    } catch (e) {
      select.innerHTML = '<option value="">Failed to load subreddits</option>';
    }
  }

  function setupReddit() {
    const btn = document.getElementById('reddit-btn');
    const select = document.getElementById('popular-subreddit-select');
    if (!btn || !select) return;
    
    loadPopularSubreddits();

    btn.addEventListener('click', async () => {
      const sub = select.value;
      if (!sub) return;
      
      btn.disabled = true;
      btn.textContent = 'Building Graph...';
      try {
        const resp = await fetch('/api/reddit', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({subreddit: sub, limit: 500})
        });
        if (resp.ok) {
          const data = await resp.json();
          await loadRuns();
          document.getElementById('run-selector').value = data.run;
          await selectRun(data.run);
        } else {
          alert('Failed to load subreddit');
        }
      } catch (e) {
          alert('Error: ' + e.message);
      } finally {
        btn.disabled = false;
        btn.textContent = 'Load Subreddit';
      }
    });
  }'''

if old_js in text:
    text = text.replace(old_js, new_js, 1)
    print("Updated JS to handle dropdown and fetching.")
else:
    print("WARNING: Could not find setupReddit JS. You may need to manually update the UI.")

p.write_text(text, encoding="utf-8")
print("Done.")
