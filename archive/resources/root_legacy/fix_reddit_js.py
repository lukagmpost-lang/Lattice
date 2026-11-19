import re
from pathlib import Path

p = Path("src/osi/static/index.html")
text = p.read_text(encoding="utf-8")

# 1. Remove any existing setupReddit function (using regex)
text = re.sub(r"  function setupReddit\(\) \{.*?\n  \}\n", "", text, flags=re.DOTALL)

# 2. Insert the new JS right before setupUpload
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
  }

  function setupUpload() {'''

if "function setupUpload() {" in text:
    text = text.replace("  function setupUpload() {", new_js, 1)
    print("Inserted new Reddit JS.")
else:
    print("ERROR: Could not find setupUpload.")

# 3. Ensure setupReddit() is called in the boot sequence
if "setupReddit();" not in text:
    text = text.replace("  setupUpload();", "  setupUpload();\n  setupReddit();", 1)
    print("Added setupReddit() to boot sequence.")

p.write_text(text, encoding="utf-8")
print("Done.")
