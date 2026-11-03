# Cuyahoga County Land Ownership — Finding

## Summary

Cuyahoga County has a public land bank system and a dispersed private property market. The land bank holds 18,000-22,000 parcels depending on how the strings are counted. No single owner string outside the land bank holds more than 50 parcels. Mailing-address clustering was tested and found to be mostly buildings and commercial mail drops, not operator clusters.

## What was built

- src/osi/loaders/cuyahoga.py — parcel fabric to bipartite graph (295,554 nodes)
- src/osi/loaders/cuyahoga_transfers.py — deed history to transfer graph (840,940 nodes)
- src/osi/lookup.py — find_person() front door, returns dossier with derived limits
- analysis/cuyahoga/ — 14 scripts that produced the numbers below

## Findings

**1. Land bank scale.** 18,186-20,501 parcels depending on definition: 18,323 (all 253 name variants, sum of total_parcels), 16,733 (three majors: City of Cleveland LRP 13,932, County LRC 1,449, East Cleveland 1,353), 18,186 (rc2 strict matcher), 20,501 (rc1 parcel-level, last transfer into LB), 22,515 (post-v6 government fix). The published figure must state which definition. County LRC is ~1,400, not the ~2,900 in earlier handoffs.

**2. The land bank is a warehouse, not a feeder.** rc1 parcel-level: 79.2% of parcels whose last transfer was into an LB are still in LB. 20.8% left. This is a floor on release rate because the transfer source returns one row per parcel (last transfer only) — a parcel that went LB then X then Y shows as never in LB. True release is above 20.8%. 34% of current inventory arrived via intra-LB reshuffle, not fresh external acquisition.

**3. Holding age is measured, not asserted.** Of 10,336 parcels currently held by a land bank, median time since most recent LB acquisition is 10 years; 48.9% not re-acquired since before 2016. Acquisition waves cluster at ~2010-2012 (foreclosure crisis, ~2,000 events, 20% of stock) and ~2022 (~800 events). Of 341 released parcels where entry and exit dates are both visible, median tenure was 1 year (mean 2.4), with 59% passing through in ≤1 year. The 5,396 total releases include those whose entry dates precede the transfer-history window and cannot be timed.

**4. CHN Housing Partners is a distributor, not a holder.** Across five name variants, CHN received 58 parcels from the land bank and transferred 578 out to ~578 individual recipients. The 335 parcels attributed to nonprofit in the follow-through table belong mostly to Habitat, Slavic Village Development, Detroit Shoreway CDC, and churches, not CHN.

**5. Three Black Knights and The Orlean Company are independent on every graph-testable axis.** Shared grantors: 1 (Cuyahoga County LRC itself; null finding). Shared grantees: 0. Shared mailing addresses: 0. This tests grantor overlap, grantee overlap, and mailing address. It does not test signatories or beneficial ownership.

**6. Private ownership is diffuse.** rc2 sweep: 31,937 owners hold 108,040 parcels at 2+ parcels any zips; 729 owners hold 20,544 at 10+ parcels and 2+ ZIPs. Public holdings are concentrated in 3-4 legal entities; private holdings are the same aggregate split into hundreds. Even at the strictest threshold, private holdings roughly equal public holdings across ~200x more entities.

**7. Mailing-address clustering is mostly buildings and mail drops.** 2,274 addresses in the graph have 3+ owners; 24,203 owners (36% of all 66,492) share a mailing address with at least two others. Classifying those 2,274 addresses by owner count and kind distribution: small_mixed 842 (37%), small_entity 670 (29%), small_household 267 (12%), mid_mixed 189, residential_building 184, commercial_drop 83, large_mixed 39. The largest addresses by owner count (553, 493, 364 owners) are a downtown Cleveland residential building, a Slavic Village residential building, and a Canton OH commercial mail drop of unrelated LLCs — not operator clusters. Small clusters (3-10 owners) are 78% of the total and are the only meaningful co-mailer signal. The same_mail edge in the graph is a correct string match but an incorrect inference of coordination for the 12% of addresses that are buildings or drops.

**8. Co-mailer candidates are surfaced, not confirmed.** The dossier for a 40-parcel owner sharing mail with three LLCs correctly labels them small_entity, not confirmed connections. Testing a co-mailer cluster requires pulling deeds where those LLCs are the parties — not deeds where the target individual is grantee. The tool's output is a candidate list, and every candidate requires primary-source verification. Two primary-source tests have now been run against the co-mailer cluster; both came back null (see Finding 9).

**9. Co-mailer cluster, SOS statutory-agent test (null).** The three small_entity LLCs sharing a mailing address with the 40-parcel owner were looked up in the Ohio SOS business registry (businesssearch.ohiosos.gov). Statutory agents:

| LLC | Entity # | Statutory Agent | Agent Address | Filed |
|---|---|---|---|---|
| 9LYVES AUTO INVESTMENTS AND CONSULTING GROUP LLC | 5463115 | KAREN C. WILLIAMS | 25606 BRECKENRIDGE DR, EUCLID OH 44117 | 08/25/2025 |
| FROMBY CONSTRUCTION | 1502433 | DEREK D FROMBY | 1487 TYLER, AKRON OH 44307 | 12/14/2016 |
| DEEN KALA OHIO HOLDING | 5544885 | REGISTERED AGENTS INC | 6545 MARKET AVE N STE 100, CANTON OH 44721 | 01/27/2026 |

Three different agents, three different cities, one of them a commercial agent service (REGISTERED AGENTS INC). No shared-agent cluster. FROMBY is an owner-operator entity (agent surname = entity name). 9LYVES uses an individual agent at a residential Euclid address, not a registered-agent firm. DEEN KALA's real principals are not in the public record because REGISTERED AGENTS INC is a pay-for-service agent. The same_mail edge remains a string match, not evidence of coordination. This is the second independent primary-source test of the co-mailer hypothesis (after the deed-signature test) and the second null result. Testing shared ownership rather than shared agent would require member/officer data, which Ohio does not publish in the free business search.

Third test: DEEN KALA deed pull. Seven documents were pulled from the Cuyahoga Recorder for DEEN KALA OHIO HOLDING. Six are mortgages; one is a deed (19476627, recorded 05/18/2026) with Elisa Ann Amaro and Joe Fransisco Alonso as grantors, notarized in Riverside County, California, and DEEN KALA as grantee. No DEEN KALA principal signs the deed—on a purchase deed only the grantor signs. The signatory on the only DEEN KALA document is the California seller, not the entity. The co-mailer cluster is now refuted across three independent axes (prior deed-signature test, SOS statutory agents, and this deed pull). The same_mail edge remains a string match, not evidence of coordination.

Note on name resolution: the full legal name is 9LYVES AUTO INVESTMENTS AND CONSULTING GROUP LLC, not the truncated 9LYVES AUTO INVESTMENTS string in the graph. The co-mailer label the dossier prints is a shortened form; the full name appears only in the SOS record.

**10. Out-of-state sellers are a real pattern in Cleveland deed transfers; out-of-state buyers are not.** The deed pull run against DEEN KALA OHIO HOLDING surfaced one purchase deed (19476627, recorded 05/18/2026) with California sellers: Elisa Ann Amaro and Joe Fransisco Alonso, notarized in Riverside County, California, conveying to an Ohio LLC as grantee. This is consistent with the prior session's deed pull, which found JAMSERIES using a Las Vegas suite and Deen Kala using a California residence. The observable signal is the out-of-state notarization: the seller did not travel to Ohio to close, which implies a remote/brokered transaction. Counterpoint: the Freedom Estates Ltd. document in the same pull (19476619) has an Ohio grantor (Duane E. Bremke, Managing Member) and an Ohio preparer (Mark F. Craig, Esq.), so the pattern is specifically on the seller side, not universal to all parties. Sample size is small (a handful of deeds from one pull); this is a candidate pattern for further testing, not a measured rate. Testing it would require pulling a random sample of recent Cuyahoga deeds and classifying grantor notarization state.

## What cannot be answered from this data

- Beneficial ownership behind Delaware LLCs (requires deed signatures or non-public filings)
- Parcel lifecycle beyond the last transfer (transfer source is a snapshot, one row per parcel)
- Who controls the pipeline (LB board composition, disposition decisions, RFPs are public record but not loaded)
- Whether specific co-mailer LLCs share control (requires deeds where those LLCs are the parties)
- Whether owner strings with similar names are the same party (classifier has 5-8% error; resolver not deployed)

## Corrections from this session

Five untraced claims were corrected. Candidate hypothesis to primary source to assertion is the pattern.

1. **17:1 public-to-private retired.** Denominator (1,064) was hand-curated, not measured. Minimum measurable private scattered-site is 20,544 parcels. Real ratio at 10+ parcels / 2+ ZIPs is 0.9:1, essentially parity.
2. **"2% release" was wrong.** Was graph-vs-graph consistency, not release rate. Corrected to 20.8% released / 79.2% held (rc1, parcel-level, last transfer).
3. **"60% held >10 years" was wrong.** Measured from first_date not last_date. Corrected to 48.9% not re-acquired since before 2016.
4. **"Third Shamsshare spelling" does not exist.** Two nodes, not three.
5. **"Shares mail with 3 LLCs = cluster" was partly refuted and partly reframed.** The three LLCs are small_entity addresses, not commercial drops. The one real signal was the two-owner spelling variation (same_name_variant). The earlier deed-based "cluster refuted" claim was logically wrong (signatories read were seller-side). The mail-address resolution is the part that holds.

## Data sources

- Cuyahoga County Fiscal Office — ArcGIS REST FeatureServer, parcel fabric
- Cuyahoga County Fiscal Office — transfer records via same service (last-transfer snapshot; full history not served)
- Ohio Secretary of State — business search, manually checked for top 14
- SEC EDGAR — Form 4 filings for PulteGroup and NVR

## Reproduce

cd ~/Desktop/OSI/Open-Source-Intelligence
python3 analysis/cuyahoga/s1.py    # LB inventory
python3 analysis/cuyahoga/rc1.py   # hold/release rate
python3 analysis/cuyahoga/rc2.py   # private-side sweep
PYTHONPATH=src python3 -m osi.lookup "ALLY, SHAMSSHARE"

Requires cuyahoga_unified.pkl, cuyahoga_transfers.pkl, and cuyahoga_transfers_raw.json on ~/Desktop/, produced by the loaders in src/osi/loaders/ and dl_transfers.py.

## What is not in the graph

- Deed signatures (would pierce Delaware nominees)
- Full parcel transfer history (would enable lifecycle)
- Campaign finance (not loaded)
- Court records (not loaded)
- Voter file (not acquired, 7 dollars from BOE)
- Out-of-county properties (Melissa Property API, paid)
- Beneficial ownership (not publicly available for LLCs)
- LB board membership and disposition decisions
