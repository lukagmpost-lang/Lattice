from pathlib import Path

p = Path("src/osi/static/index.html")
text = p.read_text(encoding="utf-8")

# 1. Remove the old onclick attribute from the button in viz.py
viz_p = Path("src/osi/viz.py")
viz_text = viz_p.read_text(encoding="utf-8")
viz_text = viz_text.replace('onclick="window.open(\'/api/graph/png/wa-real\', \'_blank\')"', '')
viz_p.write_text(viz_text, encoding="utf-8")

# 2. Add the JS listener in index.html
old_js = "  function setupRunSelector() {"
new_js = """  function setupPngExport() {
    // Attach event listener to the button inside the iframe
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

if old_js in text:
    text = text.replace(old_js, new_js, 1)
    print("Added PNG export listener to index.html.")

# 3. Call the setup function in boot
if "setupPngExport();" not in text:
    text = text.replace("  setupUpload();", "  setupUpload();\n  setupPngExport();", 1)
    print("Added setupPngExport() to boot sequence.")

p.write_text(text, encoding="utf-8")
print("Done.")
