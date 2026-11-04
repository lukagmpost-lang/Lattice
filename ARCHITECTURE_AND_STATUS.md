# OSI Architecture & Status Update (Nov 4, 2026)

## 1. The Decoupled Scraper Architecture (The Pickle Fix)
**Problem:** Running multiple background scrapers that wrote directly to `cuyahoga_unified.pkl` caused a race condition and corrupted the file (`EOFError`).
**Solution:** Scrapers are now completely decoupled from the graph.
* Scrapers read a static list (`scrape_targets.json`).
* They write raw data to `.jsonl` files (`marriage_progress.jsonl`, `courts_progress.jsonl`).
* The script `merge_jsonl_to_graph.py` safely ingests the JSONL logs and updates the `.pkl` graph.
* **Benefit:** Scrapers can run for days without risking the graph. You can resume from crashes perfectly.

## 2. Entity Resolution Rules (The "Masha Popovsky" Logic)
Because Cuyahoga County has millions of records, the merge script applies strict rules to prevent false positives:
* **Temporal Bounding:** If a court case is filed before the person was 18 (based on Voter File DOB), the edge is rejected. (e.g., preventing a 1969-born Maria Pagan from getting a 1984 divorce).
* **Ruthless Middle Initials:** `JONES, LINDA` and `JONES, LINDA D` are strictly separated unless a DOB or Address proves they are the same. (This shattered a fake mega-hub of 4 different Linda Joneses).
* **Org vs. Person Segregation:** Banks, hospitals, and LLCs are stored as `org|` nodes, not `owner|` nodes. 
* **Hospitals as Structural Anchors:** We keep hospitals (MetroHealth, UH, Lakewood) in the graph. In Cleveland, medical debt and probate lawsuits connect families. They are crucial hubs.
* **Caption Presence:** If a person's name is in the case caption, it creates a `litigated_with` edge. If their name is only mentioned elsewhere in the docket, it creates a `mentioned_in_case` edge.

## 3. Current Scraper Status & The Expansion Plan
* The background scrapers (Marriage and Courts) are currently churning through a test batch of ~2,500 targets. 
* **The Bug:** The initial `export_targets.py` only grabbed people with a comma in their name (`LAST, FIRST`), skipping ~25,000 people named `FIRST LAST`.
* **The Fix:** We rewrote `export_targets.py`. It now correctly parses and exports **all ~29,000 voter-matched identities** to `scrape_targets_full.json`.
* **Next Step:** Once the current 2,500 batch finishes, kill the scrapers, point them to the new `scrape_targets_full.json`, and restart. The social graph will expand from 186 connected people to tens of thousands.

## 4. The Social Graph & Leverage Analysis
We created `viz_social.py` to render only person-to-person edges, revealing family clusters and litigation chains. 
We ran Betweenness Centrality on this social subgraph to find the "structurally important people" (the brokers).
**Current Top 20 Brokers:**
1. CENTER, METROHEALTH MEDICAL
2. CLEVELAND, UNIVERSITY HOSPITALS OF
3. PAYNE, JOHN M.
4. WILLIAMS, DONALD J
5. SR., DONALD A. WILLIAMS
6. SOLDAN, DONALD M SR
7. GREEN, WILLIE
8. THOMPSON, DONALD A.
9. JR, DONALD THOMPSON
10. RODRIGUEZ, JOSE M.

## 5. What's Still Missing (The Roadmap)
* **eLicense Data:** The Ohio eLicense portal is built on Salesforce. It requires API emulation to bypass the UI. (Currently blocked).
* **Campaign Finance:** The Cuyahoga Board of Elections has candidate finance filings, but no bulk download.
* **Property Pruning:** Now that we have the Voter File, we should prune property-only nodes that have no DOB/Address to clean up the 300k parcel edges.
