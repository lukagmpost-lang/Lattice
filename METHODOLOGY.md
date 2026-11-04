# OSI Cuyahoga Graph — Methodology & Architecture

## 1. The Data Layers
The graph is built on four distinct layers of public records:
1. **Property (Cuyahoga Fiscal Office):** Parcels, deeds, ownership, and mailing addresses. This forms the physical and financial backbone.
2. **Identity (Cuyahoga Voter File):** 877,000 registered voters providing Date of Birth (DOB) and residential addresses. This is the anchor for entity resolution.
3. **Corporate (Ohio SOS):** LLC organizers, statutory agents, and corporate officers.
4. **Social (Probate & Common Pleas Courts):** Marriage records (ML), divorces (DR), civil lawsuits (CV), and judgment liens (JL).

## 2. Entity Resolution Rules
Because common names (e.g., "Maria Pagan") appear hundreds of times, the graph does not rely on fuzzy string matching alone. It applies three strict rules:

* **The DOB Anchor:** If a person node is matched to the Voter File, their DOB is locked. A court record cannot be attached to that person if the timeline doesn't make sense.
* **Temporal Bounding:** The court merge script enforces an age check. If a divorce was filed in 1984, it is rejected for anyone born after 1966 (preventing a 15-year-old from getting divorced).
* **Strict Middle Initials:** `PAGAN, MARIA` and `PAGANO, MARIA` are treated as different people. The script requires a full last-name match or an exact middle-initial match before merging nodes.
* **Organization Segregation:** Banks, hospitals, and government entities (e.g., MetroHealth, U.S. Bank) are stored as `org|` nodes. They are never treated as people, but they remain in the graph because they are crucial connective tissue (e.g., medical debt links families).

## 3. Graph Construction
* Scrapers read from a static target list and append raw data to `.jsonl` files (preventing pickle corruption).
* The `merge_jsonl_to_graph.py` script ingests the JSONL files, applies the entity resolution rules, and safely writes to the `.pkl` graph.
* The `viz_social.py` script isolates the person-to-person edges (marriages, divorces, lawsuits), stripping out property parcels to reveal the social dynamics.

## 4. Confidence Scoring
Edges are scored using the vendored Estorides model (NATO Admiralty standard). 
* Property records and court filings are `reliability=A` (official primary sources).
* Algorithmic candidates (like OsintHunter aliases) are `reliability=E` (tertiary).
* The confidence model requires multiple independent sources (e.g., a deed + a voter match) to push an edge into the high-confidence tier.
