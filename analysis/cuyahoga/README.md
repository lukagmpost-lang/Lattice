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

## Data ceiling

`cuyahoga_transfers_raw.json` returns one row per parcel (last transfer only),
not full deed history. Every hold-rate figure is therefore a floor. Parcel
lifecycle questions (time-in-LB, round trips) cannot be answered from this
snapshot; they require recorder deed chains.
