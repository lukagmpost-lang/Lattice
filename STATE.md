# Cuyahoga County Land Ownership — Finding

## Summary

Cuyahoga County's property power structure is public, not private. The land
bank system holds 17,997 parcels across the City, County, and suburban land
banks. Every private scattered-site landlord combined holds 1,064. Ratio 17:1.
No hidden private baron is visible at any layer of the data.

## What was built

- `src/osi/loaders/cuyahoga.py` — parcel fabric → bipartite graph (295,554 nodes)
- `src/osi/loaders/cuyahoga_transfers.py` — deed history → directed transfer graph (840,940 nodes)
- `cuyahoga_unified.pkl` — merged graph with 6 node types and 8 edge types
- Galaxy visualizations at both filtered and full-node scale

## Findings

**1. The land bank dominates.** 17,997 parcels held across the City of
Cleveland Land Reutilization Program (~14,000 under 10 spellings), the
Cuyahoga County Land Reutilization Corp (~2,900 under 16 spellings), the
East Cleveland land bank (~1,500), and suburban land banks.

**2. The land bank is a warehouse, not a feeder.** 76% of its inventory has
never been released. Of the 24% that left, 59% was internal government churn.
The remaining disposition goes primarily to HUD and nonprofits — CHN Housing
Partners, Greater Cleveland Habitat for Humanity, Slavic Village Development,
Detroit Shoreway CDC, FAMICOS Foundation, and the Elizabeth Baptist Church.
That is affordable-housing policy working as designed.

**3. Small private flippers operate at the margin.** 4,492 of the 12,006
land-bank-acquired parcels (37.4%) were resold to third parties by 558
acquirers (13.9% of 4,023). Two private entities dominate the flip tier:
Three Black Knights LLC (60 parcels resold, filed 2011) and The Orlean
Company (54 parcels resold, filed 1954). Independent operations from
opposite eras. Everyone else in the flipper list is HUD, a nonprofit, or a
deed-parsing artifact.

**4. Top individual landlord holds 48 parcels.** Ally Shamsshare, three
spellings, 48 parcels, bought one at a time from banks and individuals
2015–2026. Second: Torres, Raul at 39. This is small-scale Cleveland
landlordism — not a baron, an accumulator working the REO pipeline.

**5. Institutional SFR entered 2024–2025 but is minor.** 251 parcels
across Riparian VPC Ohio SFR Portfolio (filed Feb 2025), LMRK Owner I
(filed Oct 2025), and TH Property Owner I (filed 2022). All Delaware
LLCs. 2.3% of land-bank holdings. No ZIP overlap with land-bank
concentration — they buy where the land bank doesn't.

**6. Top five "private landlords" are single apartment buildings.**
MHG Hamptons (634 units, 27020 Cedar Rd), Vue Beachwood (349, 23210
Chagrin), Clifton Suites (133, 11118 Clifton), 12000 Edgewater (113,
Lakewood), LSB Seven Hills (91, Beck Ln). One building each, parceled
into units. Not portfolios.

## What cannot be answered

**Beneficial ownership behind Delaware LLCs.** Ohio SOS lists officers
for domestic entities only. Delaware lists registered agent and file
number, not principals. Whether a hidden structure exists behind the
Delaware LLCs (Riparian, LMRK, TH Property, Vue Beachwood, 12000
Edgewater, TH Property Owner I) cannot be determined from public data.
Would require deed signatures (Recorder documents via `book_page`) or
non-public beneficial ownership filings.

**The legal structure behind the land bank.** The City and County land
banks are public entities with appointed boards. Board membership is
public record but not loaded. Whether board members have conflicts
with private developers is a separate question, not answered here.

## Reproduce


## Data sources

- Cuyahoga County Fiscal Office — ArcGIS REST FeatureServer, parcel fabric
- Cuyahoga County Fiscal Office — transfer records via same service
- Ohio Secretary of State — business search, manually checked for top 14
- SEC EDGAR — Form 4 filings for PulteGroup and NVR, 11 officer nodes

## What is not in the graph

- Deed signatures (would pierce Delaware nominees)
- Campaign finance (not loaded)
- Court records (not loaded)
- Voter file (not acquired, $7 from BOE)
- Out-of-county properties (Melissa Property API, paid)
- Beneficial ownership (not publicly available for LLCs)
