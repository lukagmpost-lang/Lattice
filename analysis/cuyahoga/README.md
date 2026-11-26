# Cuyahoga land-bank analysis

## Inputs and data ceiling

The active loaders operate on analyst-owned files on the Desktop:

- `~/Desktop/cuyahoga_unified.pkl` — merged ownership + transfer graph
- `~/Desktop/cuyahoga_transfers.pkl` — aggregated transfer graph with source-transaction provenance
- `~/Desktop/cuyahoga_transfers_raw.json` — last-transfer snapshot

The ArcGIS downloader is retained at
`archive/resources/cuyahoga_root/dl_transfers.py`. It requests one current
transfer record per parcel, not recorder deed history. Parcel lifecycle,
round-trip, and historical flip questions therefore cannot be answered from
this snapshot; they require recorder deed chains.

Older land-bank analysis scripts (`s1.py`, `rc1.py`, `rc2.py`, and experiment
scripts) are historical artifacts under `archive/resources/`. They are not
active modules in this directory, and their historical outputs must be read
with the snapshot limitation above.

## Install

```bash
uv pip install -e '.[production]'
# Equivalent requirements-file path:
# .venv/bin/python -m pip install -r requirements-production.txt
```

## Rebuild transfer and ownership graphs

```bash
PYTHONPATH=src .venv/bin/python -B -m osi.loaders.cuyahoga_transfers \
    --raw ~/Desktop/cuyahoga_transfers_raw.json \
    --out ~/Desktop/cuyahoga_transfers.pkl

.venv/bin/python analysis/cuyahoga/merge_derive.py \
    --transfers ~/Desktop/cuyahoga_transfers.pkl \
    --out ~/Desktop/cuyahoga_unified.pkl
```

The transfer loader assigns every raw row a stable transaction ID. Aggregated
owner-pair edges retain transaction IDs, parcel IDs, row-level amounts/dates,
and book/page references so joint-party expansions can be deduplicated after
entity resolution.

## Entity resolution + pruned graph

`build_persons_enriched.py` flattens the person-owner nodes in
`cuyahoga_unified.pkl` into `data/persons_enriched.parquet`.

```bash
.venv/bin/python analysis/cuyahoga/build_persons_enriched.py
.venv/bin/python splink_graph_pipeline.py \
    --input analysis/cuyahoga/data/persons_enriched.parquet \
    --graph-input ~/Desktop/cuyahoga_transfers.pkl \
    --output-dir .
```

Outputs: `cuyahoga_resolved_clusters.parquet`,
`cuyahoga_pruned_graph.graphml`, `cuyahoga_cluster_studio.html`, and
`cuyahoga_pipeline_stats.json`. EM training is opt-in (`--train`); the default
uses the deterministic golden priors. Missing graph input is a hard error;
sample data is used only with explicit `--demo`.

After Splink clustering, `split_conflicting_clusters()` forces records apart
when both sides have different DOBs, voter IDs, or middle initials; missing
values never conflict. The cluster parquet includes `splink_cluster_id`, the
refined `cluster_id`, and `confidence_level`: `HIGH` when at least two records
share a DOB or voter ID, `LOW` otherwise. Singletons and name-only clusters are
LOW. Unresolved graph endpoints remain unresolved unless `--only-resolved` is
explicitly supplied.

The GraphML retains `book_pages` and transaction provenance. `n_transactions`
counts distinct source transaction IDs after cluster collapsing. Legacy graph
inputs without IDs are supported but flagged as having incomplete provenance.

## Entity-resolved graph visualization

```bash
.venv/bin/python visualize_resolved_graph.py \
    --graph cuyahoga_pruned_graph.graphml \
    --clusters cuyahoga_resolved_clusters.parquet \
    --output cuyahoga_resolved_graph.html \
    --spacing 1.25
```

`--spacing` controls static layout compactness; values above `1.0` increase
node separation (the default is `1.25`). Browser physics/gravity is disabled so
the deterministic layout does not move after loading.

This standalone, white-background Pyvis rendering uses the static,
community-colored style of the archived `viz.py`. It includes **every** merged
`cluster:<id>` node (including isolates) and only its direct unresolved
transaction neighbors; unresolved-only components are omitted. Hover a cluster
to inspect all merged source records and its confidence label. Gold borders mark
HIGH-confidence clusters, and directed edges retain observed transaction counts
and amounts. This is a graph visualization, not the Splink Cluster Studio.

## Multi-layer transfer + social graph

The social-enriched `cuyahoga_unified.pkl` already contains verified marriage
and court edges. Merge those existing edges with the pruned, entity-resolved
transfer graph without rerunning Splink or the scrapers:

```bash
.venv/bin/python build_cuyahoga_multilayer_graph.py \
    --transfer-graph cuyahoga_pruned_graph.graphml \
    --clusters cuyahoga_resolved_clusters.parquet \
    --unified ~/Desktop/cuyahoga_unified.pkl \
    --output cuyahoga_multilayer_graph.graphml \
    --audit cuyahoga_multilayer_audit.json

.venv/bin/python visualize_resolved_graph.py \
    --graph cuyahoga_multilayer_graph.graphml \
    --clusters cuyahoga_resolved_clusters.parquet \
    --output cuyahoga_multilayer_graph.html \
    --spacing 1.25
```

The four imported relations are `married_to`, `divorced_from`,
`litigated_with`, and `mentioned_in_case`. The last is a weaker docket-name
association, not proof that the person was a caption party or litigant. In the
HTML, transfers are gray arrows, marriages pink, divorces purple, litigation
cyan, and docket mentions dashed light gray. Social edges are undirected;
transfers retain grantor-to-grantee direction.

For the large multi-layer layout, installing the `fast` extra enables the
compiled igraph backend (`uv pip install -e '.[production,fast]'`); without it,
the renderer falls back to NetworkX, which is substantially slower for the
50,000-node component.

The mixed graph uses `MultiDiGraph` so parallel transfer and social
relationships survive. Social edges carry `directed=false`; their stored
endpoint order has no semantic direction. Case number, caption, source,
reliability, match method, and original owner pairs are retained. Identical
evidence created by cluster collapsing is deduplicated with all source pairs
preserved. Edges whose endpoints collapse to the same cluster are excluded as
self-relationships and listed in `cuyahoga_multilayer_audit.json`; they are not
silently discarded. The audit reconciles every selected input edge as written,
deduplicated, or quarantined.

Coverage is limited to records already merged into the unified input. This
stage does not claim complete county marriage or litigation coverage.

## Strict parcel-transfer network

```bash
.venv/bin/python build_parcel_transfer_network.py \
    --raw ~/Desktop/cuyahoga_transfers_raw.json \
    --clusters cuyahoga_resolved_clusters.parquet \
    --unified ~/Desktop/cuyahoga_unified.pkl \
    --output-dir .
```

Qualifying source rows must have an amount **strictly greater than $50,000**,
join different resolved clusters, and have **HIGH confidence at both
endpoints**. The network uses transaction-keyed `Cluster -> Parcel -> Cluster`
half-edges. Joint parties may create multiple associations, but parcel counts
and amounts are deduplicated by transaction ID.

Outputs:

- `high_value_parcel_network_high_conf.graphml`
- `high_value_parcel_transfer_network_high_conf.png`
- `top20_parcel_transfers.csv`
- `parcel_transfer_audit.json`

The CSV is an observed-transfer ranking for the snapshot, **not a historical
flip ranking**. If no rows satisfy all filters, the GraphML and CSV are empty,
the PNG explicitly reports no qualifying data, and the audit records each
exclusion stage. The filters are never relaxed to manufacture a nonempty
network.
