# Cuyahoga County Land Ownership — Finding

## Summary

Cuyahoga County's property power structure is concentrated on the public
side, not the private side. Three to four public legal entities (City of
Cleveland LRP, Cuyahoga County LRC, East Cleveland LB, plus suburban LBs)
hold ~18,000 parcels. The top 729 private owners (10+ parcels, 2+ ZIPs)
hold ~20,500. Roughly 32,000 smaller private owners hold another ~108,000.

The right claim is not a public-vs-private ratio. It is that **public
holdings are concentrated in a handful of legal entities while private
holdings are diffuse across tens of thousands.** No hidden private baron
is visible in this data — not because one can't exist behind the LLCs,
but because nothing at this layer shows concentration into a few hands.

## What was built

- `src/osi/loaders/cuyahoga.py` — parcel fabric → bipartite graph (295,554 nodes)
- `src/osi/loaders/cuyahoga_transfers.py` — deed history → directed transfer graph (840,940 nodes)
- `cuyahoga_unified.pkl` — merged graph
- `analysis/cuyahoga/` — the scripts that produced the findings below

## Findings

**1. Public land holdings total ~18,000 parcels across ~250 name variants
and 3–4 legal entities.** s1 matcher: 18,323 total, 16,733 three-majors
(CoC LRP 13,932 / County LRC 1,449 / East Cleveland LB 1,353), 18,186
under rc2's stricter LB match. rc1's parcel-level count (last transfer
was into LB) is 20,501 — higher than G's node sum because a parcel can
appear under an LB variant in the transfer graph not present in the
parcel fabric. **All four numbers are in the same family; 18,000–20,500
is the honest range.**

**2. Cuyahoga County LRC holds ~1,400 parcels, not ~2,900.** The previous
2,900 figure is not reproducible. Current holdings: `CUYAHOGA COUNTY LAND
REUTILIZATION CORPORATION` 1,204 + `...CORP` 130 + 21 subsidiary LLCs
(CCLRC CLEVELAND IV, CCLRC ARBOR PARK, etc.) at 71 total ≈ 1,405. The
gap between this and 2,900 is unexplained and the 2,900 should not be
quoted.

**3. The land bank is a warehouse, not a feeder.** rc1 parcel-level
analysis: **79.2% of parcels whose last transfer was into an LB are still
in LB. 20.8% left.** This is a **floor on the release rate** because the
transfer source returns one row per parcel (last transfer only) — a parcel
that went `LB → X → Y` shows as "never in LB" and is not counted as
released. True release is somewhere above 20.8%. The prior 76%/24%
handoff figure is within definitional tolerance of 79.2%/20.8% and is not
contradicted.

**4. About 34% of current inventory arrived via intra-LB reshuffle.** Of
the 20,501 parcels currently held by an LB, 7,036 (34.3%) arrived via a
transfer whose grantor was also an LB. These are not fresh acquisitions
from private owners; they are inter-agency transfers (City → County, City
→ subsidiary LLC, name-variant cleanup). This is a real finding about
pipeline structure: **one parcel in three currently in a land bank got
there by another land bank handing it over.**

**5. CHN Housing Partners is a distributor, not a holder.** Across five
name variants (CHN, CNN, CHN PARNTERS, trailing comma, trailing period),
CHN received 58 parcels from the land bank and transferred **578 parcels
out** to ~578 individual recipients (weights of 1, mostly). CHN is the
primary pass-through from LB inventory to individual owner-occupants in
this data. It is not the pipeline-holding nonprofit — the ~335 parcels
attributed to "nonprofit" in the follow-through table belong mostly to
Habitat, Slavic Village Development, Detroit Shoreway CDC, and churches,
not CHN.

**6. Three Black Knights and The Orlean Company are independent on every
graph-testable axis.** Shared grantors: 1 (Cuyahoga County LRC itself —
every LB acquirer shares it; null finding, not coordination). Shared
grantees: 0. Shared mailing addresses: 0. TBK filed 2011, Orlean filed
1954. **Caveat:** this tests grantor overlap, grantee overlap, and mailing
address. It does not test signatories or beneficial ownership. The narrow
company-only Orlean set (excluding person nodes named Orlean) has not
been re-run; the broad set produced the clean null.

**7. Private ownership is diffuse.** rc2 sweep:

| Filter | Owners | Parcels |
|---|---|---|
| ≥2 parcels, any zips | 31,937 | 108,040 |
| ≥2 parcels, ≥2 zips | 14,331 | 60,257 |
| ≥5 parcels, any zips | 3,556 | 41,994 |
| ≥5 parcels, ≥2 zips | 2,433 | 31,093 |
| ≥10 parcels, any zips | 1,017 | 26,348 |
| ≥10 parcels, ≥2 zips | 729 | 20,544 |

**Even at the strictest threshold (10+ parcels, 2+ ZIPs), the top 729
private owners hold 20,544 parcels — slightly more than all public
land-bank holdings combined (18,186–20,501), spread across ~200x more
entities.** Public holdings are one aggregate; private holdings are the
same aggregate split into hundreds. **That is the concentration finding.**

**8. The former "1,064 private scattered-site" denominator is not
reproducible from this graph under any standard threshold.** The
narrowest possible measurement gives 20,544 parcels. The 1,064 figure
was likely a hand-curated subset of named private landlords, not a
computed total. It should not be used as a denominator for any ratio.

**9. Other findings unchanged from prior version.** Top individual
landlord Ally Shamsshare at 48 parcels across three spellings; second
Torres, Raul at 39. Institutional SFR (Riparian, LMRK, TH Property) at
~251 parcels, 2.3% of land-bank holdings, in ZIPs with no land-bank
concentration. Top "private landlords" are mostly single apartment
buildings (MHG Hamptons, Vue Beachwood, Clifton Suites, 12000 Edgewater,
LSB Seven Hills), not portfolios. These were not re-tested this session
and stand as previously found.

## What cannot be answered from this data

**Beneficial ownership behind LLCs.** Ohio SOS lists officers for
domestic entities; Delaware lists registered agent only. Whether a hidden
structure exists behind the Delaware LLCs (Riparian, LMRK, TH Property,
Vue Beachwood, 12000 Edgewater, TH Property Owner I) requires deed
signatures or non-public beneficial ownership filings.

**Parcel lifecycle.** The transfer source is a **last-transfer snapshot,
one row per parcel**. It cannot answer: how long parcels sit in LB, how
often released parcels return, whether released parcels became housing
or paper transfers. The 20.8% release rate is a floor. Answering these
requires recorder deed chains (captcha-gated, one parcel at a time).

**Who controls the pipeline.** Board membership of City of Cleveland LRP
and Cuyahoga County LRC is public record but not loaded. Disposition
decisions, RFPs, and selection criteria are not in this graph.

**Shared signatories between TBK and Orlean.** SOS officer records would
answer this directly. The current graph tests grantors, grantees, and
mailing addresses only.

## Corrections from this session

The prior version of this document (commit `1d31888`) claimed "17:1 public
to private." That claim is **retired** as of commit `5712ea8` and this
document. Three specific errors were found:

1. **Structural.** 17:1 compared a sector total (all land banks) against a
   subset of the private sector (1,064 named scattered-site landlords). The
   correct comparison is per-entity concentration, in Finding 7 above.
   Public holdings are concentrated; private holdings are diffuse. Both
   facts are true and neither supports "17:1."
2. **Denominator.** The 1,064 figure was not produced by any threshold in
   the current graph. Minimum measurable private scattered-site is 20,544
   parcels.
3. **Transient.** During this session I briefly claimed "land banks release
   only 2%" from a graph-vs-graph comparison. That was wrong — the two
   graphs measured the same population by different methods, not release
   behavior. rc1 parcel-level analysis gives 79.2%/20.8%, which is the
   figure in this document.

Additionally, the Cuyahoga County LRC figure of ~2,900 in the prior
version is not reproducible; actual is ~1,400 (Finding 2). The prior
version's claim that CHN "is affordable-housing policy working as
designed" was receipt-based inference; CHN's actual behavior (58 in / 578
out) is a pass-through to individual recipients, which may be affordable
housing delivery or may be something else — the graph does not distinguish.

## Data sources

- Cuyahoga County Fiscal Office — ArcGIS REST FeatureServer, parcel fabric
- Cuyahoga County Fiscal Office — transfer records via same service
  (last-transfer snapshot; full history not served)
- Ohio Secretary of State — business search, manually checked for top 14
- SEC EDGAR — Form 4 filings for PulteGroup and NVR, 11 officer nodes

## Reproduce


Requires `cuyahoga_unified.pkl`, `cuyahoga_transfers.pkl`, and
`cuyahoga_transfers_raw.json` on `~/Desktop/`, produced by the loaders in
`src/osi/loaders/` and `dl_transfers.py`.

## What is not in the graph

- Deed signatures (would pierce Delaware nominees)
- Full parcel transfer history (would enable lifecycle)
- Campaign finance (not loaded)
- Court records (not loaded)
- Voter file (not acquired, $7 from BOE)
- Out-of-county properties (Melissa Property API, paid)
- Beneficial ownership (not publicly available for LLCs)
- LB board membership and disposition decisions
