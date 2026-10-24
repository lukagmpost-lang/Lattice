# Lattice

Local multi-layer graph of public social relations. Accounts are nodes, public relations are weighted edges, and each relation type is a layer.

## Try it

`examples/` holds the manual test inputs.

- `examples/simple.csv` is a weighted edge list. Alice, Bob, and Carol form a triangle, and Dave is tied to Alice.
- `examples/simple.json` is NetworkX node-link JSON: a path from `a` to `c` through `b`.
- `examples/simple.graphml` has four nodes in two communities. Alice and Bob are east, Carol and Dave are west, and the edge from Bob to Carol is the bridge.

```bash
python3 main.py --source file --path examples/simple.csv --save-run simple-v1
python3 -m osi.ask --run simple-v1 "top 5 by pagerank"
```

The same two commands work with `examples/simple.json` and `examples/simple.graphml`.

## Web

```bash
uv pip install -e '.[web,fast,dev]'
uvicorn osi.server:app --host 0.0.0.0 --port 7860
```

## What it will collect

| Source | Relation | Access |
| --- | --- | --- |
| GitHub | followers, following, mutual | Public REST API, at most 2 pages of 100 |
| Reddit | public comments to subreddits | Official OAuth API, at most 100 comments |
| Steam | friends and owned games | Web API, profile must be public, caps 300 friends and 200 games |
| Spotify | the token owner's public playlists | User token only, caps 20 playlists and 100 tracks |
| Telegram | gifts displayed on a profile | Bot API `getUserGifts`, at most 2 pages of 50. Hidden gifts and hidden senders are dropped |
| File | any of the above, plus `same_as` links you assert | JSON you already have |

Private Telegram channels, gifts that are not displayed, and anonymous page scraping are not implemented. There is no score for exploiting a person or a community.

## Graph file

```json
{
  "nodes": [{"platform": "github", "account_id": "ada", "label": "ada"}],
  "edges": [{"source": "github:ada", "target": "github:grace", "layer": "mutual", "weight": 1}],
  "same_as": [{"platform": "github", "account_id": "ada", "same_platform": "reddit", "same_account_id": "ada"}]
}
```

`same_as` is stored only when you assert it. The tool does not guess that two accounts are the same person.

## Tests

```bash
PYTHONPATH=src python3 -m pytest
```

## LLM Provider

The tool uses Groq's free tier by default. No credit card required.

1. Get a free key at https://console.groq.com/keys
2. Add it to .env:
       LLM_API_KEY=your_key_here

The default model is llama-3.3-70b-versatile. If you hit the 1,000 requests/day limit, switch to llama-3.1-8b-instant in .env for 14,400 requests/day.

---

## Link Prediction on the Reddit Hyperlink Graph

**Result:** Stripping the top-100 hubs from Adamic-Adar's scoring graph improves its ranking of future subreddit-link pairs on the same candidate pool.

**Setup:** 2,000-node non-hub universe, 2-hop candidate pool, three temporal splits. Reproducible via `hub0_check.py` (single verified result) and `sweep_fixed.py` (3-split × 5-cutoff robustness). Both run with `PYTHONHASHSEED=0` for deterministic tie-breaking. A hub=0 identity check confirms the two scorers collapse to bit-identical output when nothing is stripped (`Δ AP = 0.0000000000e+00`).

### Main result (2016-01-01, cutoff=100)

| Metric | AA with hubs | AA stripped | Δ |
|---|---|---|---|
| P@100 | 18% | 49% | +31 pt |
| AP | 0.0469 | 0.0699 | **+0.023** |

### Cutoff sweep (Δ AP)

| Cutoff | 2015-07 | 2016-01 | 2016-07 |
|---|---|---|---|
| 10 | +0.0039 | +0.0033 | +0.0014 |
| 50 | +0.0086 | +0.0122 | +0.0050 |
| **100** | **+0.0113** | **+0.0230** | **+0.0065** |
| 300 | −0.0080 | +0.0032 | +0.0028 |

Cutoff 100 is the peak on every split — reproducible structure, not a lucky pick. Paired-bootstrap 95% CIs exclude zero on every positive row and on the one negative row (2015-07 at 300). Aggressive removal (300 hubs, 1.3% of nodes) can *hurt* by deleting genuine interaction signal alongside the shortcut.

### Mechanism (2016-01-01, cutoff 100)

The two scoring graphs share only 38 of their top-100 predictions (see `diff_top100.py`, `inspect_top.py`):

- 62 pairs unique to full scoring sit at the **99.4th percentile of endpoint degree**, hit at 16%.
- 62 pairs unique to stripped scoring sit three percentile points lower, hit at **66%**.

Full-scoring top-100 is dominated by the very largest subreddits — subs that already link everywhere and don't form new outbound links to each other.

### Retracted claims

Earlier drafts of this analysis reported a "74% accuracy" figure (pair-orientation bug: reversed `(u,v)` pairs missed lookups), a "200× lift" (compared against whole-graph base rate instead of pool base rate), and a "40.6% unreachable bridge class" (74% of that class was a hub-stripping artifact, not a genuine blind spot). All are retracted. The number that survives is +0.023 AP.

### Recall ceiling

12.5% at K=5000 against an 89% reachable ceiling. This is a shortlist generator, not a predictor.

### Product recommendation

Expose hub cutoff as a degree percentile (highest few percent), not a fixed count. Do not promise a precision number — the effect size is split-dependent (+0.0065 to +0.023 at cutoff 100).
