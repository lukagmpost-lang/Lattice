# Archived / Resource Code

This directory contains code that is not part of the active OSI pipeline but is preserved for reference.

## Structure

- `analysis_tools/` — 11 legacy graph analysis scripts (0% test coverage)
- `loaders/` — 6 legacy/deprecated data loaders
- `scripts/` — 21 standalone analysis/CLI scripts with hardcoded paths (0% coverage)

## Active Pipeline

The active, tested modules remain in `src/osi/` and `src/osi/loaders/`:

- `names.py` — Canonical name parsing & identity matching
- `loaders/merge_jsonl_to_graph.py` — Verified court/marriage merge
- `loaders/courts_background.py` — Court scraper
- `loaders/marriage_background.py` — Marriage scraper
- `loaders/voter_file.py` — Voter file enrichment
- `loaders/cuyahoga.py` — Cuyahoga ownership loader
- `loaders/cuyahoga_transfers.py` — Deed transfers loader
- `loaders/slack.py`, `telegram.py`, `whatsapp.py` — Chat loaders
- `server.py` — FastAPI server with auth
- `store.py` — SQLite run store
- `graph_utils.py` — Graph helpers
- `answer.py`, `converse.py` — Q&A pipeline
- `analysis.py` — Centrality, communities, health

## Tests

Run with `PYTHONPATH=src pytest -q` — currently 283 passed, 10 skipped.
