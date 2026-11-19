# Cuyahoga land-bank analysis

Operates on pickles on the analyst's Desktop, produced by `src/osi/loaders/`:

- `~/Desktop/cuyahoga_unified.pkl` — merged ownership + transfer graph
- `~/Desktop/cuyahoga_transfers.pkl` — transfer-only graph
- `~/Desktop/cuyahoga_transfers_raw.json` — last-transfer snapshot

Regenerate with `dl_transfers.py` → `merge_derive.py` → `fix_v5.py`. `load_sos.py`
and `edgar_load.py` add SOS/SEC layers to the unified graph.

## Analysis scripts (produced the findings)

| File | Purpose | Output |
|---|---|---|
| `rc1.py` | Parcel-level hold vs release rate | 79.2% held / 20.8% released (floor) |
| `rc2.py` | Private-side concentration sweep | Retires the 17:1 ratio |
| `s1.py` | LB inventory: all / majors / strict | 18,323 / 16,733 / 18,186 parcels |
| `experiments_ab.py` | TBK vs Orlean + nonprofit follow-through | Independence holds; CHN is distributor |
| `experiments_ab_v2.py` | Same, with per-transfer double-count fix | Superseded by v3 |
| `experiments_ab_v3.py` | Permissive LB matcher + diagnostic pre-flight | Diagnostic version |

## Pipeline scripts

`dl_transfers.py`, `merge_derive.py`, `fix_v5.py`, `load_sos.py`, `edgar_load.py`,
`audit_transfers.py`, `audit_fix.py`.

## Entity resolution + pruned graph

`build_persons_enriched.py` flattens the person-owner nodes in
`cuyahoga_unified.pkl` into `data/persons_enriched.parquet`.  The production
`persons_enriched.parquet` referenced by earlier notes was not present in the
repository, so this derived table is the current input.

`splink_graph_pipeline.py` resolves duplicate owners with the golden-test
Splink settings, relabels the directed transfer graph with cluster IDs, and
prunes dead ends while preserving every cycle:

```bash
.venv/bin/python analysis/cuyahoga/build_persons_enriched.py
.venv/bin/python splink_graph_pipeline.py \
    --input analysis/cuyahoga/data/persons_enriched.parquet \
    --graph-input ~/Desktop/cuyahoga_transfers.pkl \
    --output-dir .
```

Outputs: `cuyahoga_resolved_clusters.parquet`,
`cuyahoga_pruned_graph.graphml`, `cuyahoga_cluster_studio.html`, and
`cuyahoga_pipeline_stats.json`.  EM training is opt-in (`--train`); the
default uses the deterministic golden priors, which keep Jaro-Winkler name
variants mergeable on sparse Cuyahoga fields.

After Splink clustering, `split_conflicting_clusters()` forces records apart
when both sides have different DOBs, voter IDs, or middle initials; missing
values never conflict.  The cluster parquet includes the raw Splink ID
(`splink_cluster_id`), the refined `cluster_id`, and a `confidence_level`:
`HIGH` when at least two records in the cluster share a DOB or voter ID, `LOW`
otherwise.  The refined IDs and confidence labels are also used by the
GraphML cluster nodes and the Cluster Studio dashboard.

## Data ceiling

`cuyahoga_transfers_raw.json` returns one row per parcel (last transfer only),
not full deed history. Every hold-rate figure is therefore a floor. Parcel
lifecycle questions (time-in-LB, round trips) cannot be answered from this
snapshot; they require recorder deed chains.
