# Cuyahoga County Land Ownership — Preliminary Finding

## Summary

Cuyahoga County has a public land bank system and a dispersed private
property market. The land bank is the largest single holder. No
concentration is visible under any single owner name in the current
graph. Mailing-address clustering and beneficial-owner structure are
untested.

## What was built

- `src/osi/loaders/cuyahoga.py` — parcel fabric → bipartite graph
- `src/osi/loaders/cuyahoga_transfers.py` — deed history → transfer graph
- `cuyahoga_unified.pkl` — merged graph (not in repo; schema in schema_dump)

## Findings (measured, with caveats)

**1. Land bank scale.**
Parcels whose most recent transfer was into a land bank: 22,931.
Parcels whose most recent transfer was out: 5,884.
Naive release rate: 20.4% (cumulative snapshot; not cohort-adjusted).

**2. Disposition.**
Of parcels released by land banks: 3,149 went directly to individual
recipients (3,001 unique), 879 to entities (469), 345 to nonprofits (151),
7,137 to other government entities (mostly internal self-transfer).
Direct-to-individual is the dominant external path.

**3. Private ownership dispersion.**
Owner-string threshold sweep (not de-duplicated by mailing address or
entity structure):

| Threshold | Owners | Parcels held |
|---|---|---|
| 3+ parcels | 10,459 | 56,619 |
| 5+ parcels | 3,343 | 33,188 |
| 10+ parcels | 876 | 17,999 |
| 20+ parcels | 254 | 10,017 |

Caveat: this sweep lumps apartments parceled into condo units, banks,
government, and institutions into the "private" set. Not yet cleaned.

**4. No visible single-name accumulator.**
The largest single owner string in the non-land-bank set holds <50
parcels. Mailing-address clustering (co-owners sharing a mailbox) has
not been run to test whether multiple strings represent one party.

## What cannot be answered

- Beneficial ownership behind Delaware LLCs (requires deed signatures or
  non-public filings)
- Land bank board composition and conflicts of interest (public record,
  not loaded)
- Forfeiture pipeline control (requires county auditor/treasurer records)
- Whether multiple owner strings represent one beneficial owner
  (mailing-address clustering not yet run)

## Known data issues

- Owner classifier has estimated 5–8% error, not measured against a
  frozen test set
- The SFR parcel count (251 unique) differs from the variant-inclusive
  count (422); unique parcel IDs not yet verified across all owner
  variants
- Parcel-owner relationships are snapshots (current owner only), not
  history
- The 1,005 entry `labeled_pairs.json` mixes spelling variants with real
  ownership changes; not usable as resolver training data without
  relabeling

## Reproduce

Scripts not yet in repo. To be added at `scripts/cuyahoga/`:
- download transfers
- merge + derive unified pickle
- classifier application
- reconciliation and threshold sweep

## Data sources

- Cuyahoga County Fiscal Office — ArcGIS REST FeatureServer
- Ohio Secretary of State — business search (top 14 entities only)
- SEC EDGAR — Form 4 filings for PulteGroup and NVR

## What is not in the graph

- Deed signatures (pierce Delaware nominees)
- Campaign finance
- Court records
- Voter file
- Beneficial ownership
- Mailing-address clustering (planned)
- Board and appointment records (planned)
