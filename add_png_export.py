from pathlib import Path

p = Path("/Users/2950639/Desktop/OSI/Open-Source-Intelligence/src/osi/viz.py")
text = p.read_text(encoding="utf-8")

if "download-png-btn" in text:
    print("PNG export already exists.")
    raise SystemExit(0)

# Find the end of the _inject_extras function where we write to the file
old_end = '''    html = html.replace("<body>", "<body>" + legend + isolate_js)
    out.write_text(html, encoding="utf-8")'''

new_end = '''    png_button = """
    <div style="position:absolute; top:14px; right:14px; z-index:9999;">
        <button id="download-png-btn" style="font-family:inherit; font-size:12px; padding:8px 14px; background:#161616; color:#fff; border:1px solid #444; border-radius:4px; cursor:pointer;">
            Save as PNG
        </button>
    </div>
    <script>
    document.getElementById('download-png-btn').addEventListener('click', function() {
        // Find the main canvas inside the pyvis network container
        var canvas = document.querySelector('#mynetwork canvas');
        if (!canvas) {
            alert('Canvas not found. Try again after the graph stabilizes.');
            return;
        }
        // Create a temporary link to download the canvas data
        var url = canvas.toDataURL('image/png');
        var a = document.createElement('a');
        a.href = url;
        a.download = 'network_graph.png';
        a.click();
    });
    </script>
    """

    html = html.replace("<body>", "<body>" + legend + isolate_js + png_button)
    out.write_text(html, encoding="utf-8")'''

if old_end in text:
    text = text.replace(old_end, new_end, 1)
    p.write_text(text, encoding="utf-8")
    print("Success: Added PNG export button to viz.py.")
else:
    print("WARNING: Could not find the target text in _inject_extras.")
