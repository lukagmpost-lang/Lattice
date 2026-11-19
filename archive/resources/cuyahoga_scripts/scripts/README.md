# Cuyahoga pipeline scripts

Scripts that produced cuyahoga_unified.pkl and the numbers in STATE.md.

## Chain (in order)

1. dl_transfers.py -- downloads 499k deed records from Cuyahoga ArcGIS -> cuyahoga_transfers_raw.json
2. src/osi/loaders/cuyahoga.py -- parcel fabric JSON -> ownership graph
3. src/osi/loaders/cuyahoga_transfers.py (copy of audit_transfers.py) -- deed JSON -> transfer graph -> cuyahoga_transfers.pkl
4. merge_derive.py -- merges ownership + transfer, adds same_mail / sold_to / per-owner aggregates -> cuyahoga_unified.pkl
5. load_sos.py -- adds Ohio SOS entities (currently 14 rows from sos_pass2.csv)
6. edgar_load.py -- adds SEC EDGAR officers (Pulte, NVR)
7. fix_v5.py -- classifier v5
8. classify_v6.py -- classifier v6 (82.9% on frozen test set, replaces v5 labels)
9. fix_government.py -- post-classifier government reclassification

## Classifier measurement

- make_testset.py / make_testset_v2.py -- build the frozen 280-name test set -> analysis/cuyahoga/data/classifier_testset.csv
- autolabel.py -- helper for initial labeling
- measure_classifier.py -- measures classifier accuracy against the frozen set

## Downstream analysis

- recount_public.py -- LB recount after the government fix (22,515 parcels)
- cohort_release.py, cohort_v2.py -- holding-age / cohort release analysis
- dedup_check.py -- parcel-ID uniqueness check (165,948 nodes / 165,948 unique PIDs / 0 duplicates)
- cluster_probe.py -- book_page extractor for the Shamsshare cluster
- rec.py -- analyst notes

## Inputs the scripts depend on

The three parcel JSONs (cuyahoga_res_full.json 211 MB, cuyahoga_nonres_full.json 30 MB) were produced by curl commands not saved to any script. Regenerate from the Cuyahoga FeatureServer by querying residential and non-residential parcels separately.

cluster_deeds.json on Desktop is empty (2 bytes). The five Shamsshare deeds exist only as PDFs, not as a serialized file.

## What was never saved

The galaxy renderer that produced cuyahoga_galaxy.png and cuyahoga_galaxy_allnodes.png was inline Python pasted into a terminal, never written to a file. Ego-graph render is a from-scratch task, now implemented in src/osi/lookup.py as render_ego().

## Data directory

analysis/cuyahoga/data/ holds the small inputs needed for reproduction:
- classifier_testset.csv -- 280-name frozen test set
- sos_pass2.csv, ohio_sos_lookup.csv -- 14 Ohio SOS entity records
- labeled_pairs.json -- 1,005 grantee-owner pairs (label quality low; see STATE.md)
