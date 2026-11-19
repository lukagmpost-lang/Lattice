import sys
from pathlib import Path

sys.path.insert(0, '/Users/2950639/Desktop/OSI/Open-Source-Intelligence/src')

from osi.loaders.whatsapp import _parse_export
from osi.commitments import extract_commitments, save_commitments, detect_violations
from osi.framing import extract_framings, save_framings


def run():
    chat_path = '/Users/2950639/Downloads/_chat.txt'
    print("=== NIGHT JOB STARTING ===", flush=True)
    print("Parsing chat...", flush=True)
    _, messages = _parse_export(chat_path)
    print(f"Total messages: {len(messages)}", flush=True)

    # --- 1. COMMITMENTS ---
    print("\n=== EXTRACTING COMMITMENTS ===", flush=True)
    result = extract_commitments(messages, limit=1500)

    # The extractor now returns a dict with "commitments" and "directives"
    if isinstance(result, dict):
        cs = result.get("commitments", [])
        directives = result.get("directives", [])
        print(f"Found {len(cs)} commitments and {len(directives)} directives.", flush=True)
    else:
        cs = result
        print(f"Found {len(cs)} commitments.", flush=True)

    if cs:
        print("Saving commitments...", flush=True)
        save_commitments(cs)

        print("\n=== DETECTING VIOLATIONS ===", flush=True)
        cs = detect_violations(cs, messages, window=400, sleep_seconds=20)
        save_commitments(cs)
        print("Violations saved.", flush=True)
    else:
        print("No commitments found, skipping violations.", flush=True)

    # --- 2. FRAMINGS ---
    print("\n=== EXTRACTING REMAINING FRAMINGS ===", flush=True)
    rows = extract_framings(messages, batch=20, start=200, limit=2500, sleep=20)
    print(f"Found {len(rows)} new framings. Saving...", flush=True)
    if rows:
        save_framings(rows)

    print("\n=== JOB COMPLETE ===", flush=True)


if __name__ == "__main__":
    run()
