from pathlib import Path

p = Path("src/osi/loaders/reddit.py")
text = p.read_text(encoding="utf-8")

old = '''        graph.nodes[author]["message_count"] = graph.nodes[author].get("message_count", 0) + 1'''

new = '''        if not graph.has_node(author):
            graph.add_node(author, message_count=0)
        graph.nodes[author]["message_count"] = graph.nodes[author].get("message_count", 0) + 1'''

if old in text:
    text = text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    print("Success: Restored the node creation logic.")
else:
    print("ERROR: Could not find the target line.")
