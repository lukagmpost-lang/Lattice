from pathlib import Path
import re

# 1. Fix the HTML layout
p = Path("src/osi/static/index.html")
text = p.read_text(encoding="utf-8")

new_controls = '''<section class="controls">
  <label for="run-selector">Run</label>
  <select id="run-selector"><option value="">loading...</option></select>
  
  <label class="os-btn">
    Upload chat
    <input type="file" id="file-input" style="display:none">
  </label>
  
  <span style="color:var(--muted); font-size:12px; margin:0 8px;">OR</span>
  
  <select id="popular-subreddit-select" style="padding:8px 12px; border:1px solid var(--line); font-family:inherit; font-size:13px; min-width:180px;">
    <option value="">Loading subreddits...</option>
  </select>
  <button class="os-btn" id="reddit-btn" type="button">Load Subreddit</button>
</section>'''

# Replace everything inside <section class="controls"> ... </section>
text = re.sub(r'<section class="controls">.*?</section>', new_controls, text, flags=re.DOTALL)

# 2. Fix the PNG button in viz.py to remove the hardcoded onclick
viz_p = Path("src/osi/viz.py")
viz_text = viz_p.read_text(encoding="utf-8")
viz_text = viz_text.replace("onclick=\"window.open('/api/graph/png/wa-real', '_blank')\"", "")
viz_p.write_text(viz_text, encoding="utf-8")

# 3. Add the JS listener for the dynamic PNG export
js_script = """  function setupPngExport() {
    const iframe = document.getElementById('graph-iframe');
    if (!iframe) return;
    iframe.addEventListener('load', () => {
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      const btn = doc.getElementById('download-png-btn');
      if (btn) {
        btn.addEventListener('click', () => {
          const runId = state.current;
          if (runId) window.open('/api/graph/png/' + encodeURIComponent(runId), '_blank');
        });
      }
    });
  }

  function setupRunSelector() {"""

if "function setupPngExport()" not in text:
    text = text.replace("  function setupRunSelector() {", js_script, 1)
    text = text.replace("  setupUpload();", "  setupUpload();\n  setupPngExport();", 1)

p.write_text(text, encoding="utf-8")
print("Fixed HTML alignment and PNG export logic.")
