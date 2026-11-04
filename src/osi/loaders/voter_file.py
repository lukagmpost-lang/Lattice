"""Enrich person nodes with Cuyahoga voter file data.

Does NOT create voter nodes. For each existing `owner|` node with kind=person,
looks up the voter file by name and attaches DOB, residential address, and
voter_id as node attributes when the match is unique. Ambiguous matches get
all candidates stored under `voter_candidates` and the node is flagged.

Match order:
  1. (last, first, dob) — exact, when the node already has a DOB
  2. (last, first) + address match — disambiguated by parcel or mailing address
  3. (last, first, middle_initial) — unique name match only
"""
from __future__ import annotations

import csv
import os
import pickle
import re
import sys
from collections import defaultdict


def _u(s):
    return "" if s is None else re.sub(r"\s+", " ", str(s)).strip().upper()


def name_parts_graph(name):
    """Extract (LAST, FIRST, MID) from an owner node name.

    Handles both 'LAST, FIRST MIDDLE' and 'FIRST MIDDLE LAST'.
    Returns None if the name doesn't parse as a person.
    """
    n = _u(name)
    if "," in n:
        last, rest = n.split(",", 1)
        tokens = rest.split()
        first = tokens[0] if tokens else ""
        mid = tokens[1] if len(tokens) > 1 else ""
    else:
        tokens = n.split()
        if len(tokens) < 2:
            return None
        first = tokens[0]
        last = tokens[-1]
        mid = tokens[1] if len(tokens) > 2 else ""
    if not last or not first:
        return None
    return (last, first, mid[:1])


def name_parts_voter(row):
    last = _u(row.get("LAST_NAME"))
    first = _u(row.get("FIRST_NAME"))
    mid = _u(row.get("MIDDLE_NAME"))
    if not last or not first:
        return None
    return (last, first, mid[:1])


def build_voter_index(csv_path):
    """Index voters by (last, first, mid_initial). Also returns a DOB index
    and an address index for secondary matching."""
    by_name = defaultdict(list)
    by_name_no_mid = defaultdict(list)
    by_name_dob = defaultdict(list)
    by_addr = defaultdict(list)
    n = 0
    with open(csv_path, "r", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            n += 1
            parts = name_parts_voter(row)
            if not parts:
                continue
            rec = {
                "voter_id": _u(row.get("SOS_VOTERID")),
                "last": parts[0], "first": parts[1], "mid": parts[2],
                "dob": _u(row.get("DATE_OF_BIRTH")),
                "status": _u(row.get("VOTER_STATUS")),
                "party": _u(row.get("PARTY_AFFILIATION")),
                "addr1": _u(row.get("RESIDENTIAL_ADDRESS1")),
                "city": _u(row.get("RESIDENTIAL_CITY")),
                "zip": _u(row.get("RESIDENTIAL_ZIP")),
            }
            by_name[parts].append(rec)
            by_name_no_mid[(parts[0], parts[1])].append(rec)
            if rec["dob"]:
                by_name_dob[(parts[0], parts[1], rec["dob"])].append(rec)
            if rec["addr1"] and rec["zip"]:
                # address key: normalized street + zip
                addr_key = (_u(rec["addr1"]), rec["zip"][:5])
                by_addr[addr_key].append(rec)
            if n % 100000 == 0:
                print(f"  indexed {n:,} voters...", file=sys.stderr, flush=True)
    print(f"  total voters indexed: {n:,}", file=sys.stderr)
    return {"by_name": by_name, "by_name_no_mid": by_name_no_mid, "by_name_dob": by_name_dob, "by_addr": by_addr}


def _collect_node_addresses(G, node):
    """Return a set of (street, zip) tuples for addresses connected to the node."""
    addrs = set()
    for nb in G.neighbors(node):
        if nb.startswith("parcel|"):
            pd = G.nodes[nb]
            situs = _u(pd.get("situs_addr") or pd.get("situs") or pd.get("address"))
            z = _u(pd.get("situs_zip") or pd.get("parcel_zip") or pd.get("zip"))
            if situs:
                addrs.add((situs, z[:5] if z else ""))
        elif nb.startswith("mail|"):
            md = G.nodes[nb]
            street = _u(md.get("street") or nb[5:].split("|")[0])
            zipc = _u(md.get("zip") or (nb[5:].split("|")[1] if "|" in nb[5:] else ""))
            if street:
                addrs.add((street, zipc[:5]))
    return addrs


def match_node(node_name, node_data, addresses, index):
    """Return (match_type, matched_records).

    match_type ∈ {"dob", "address", "name_unique", "name_ambiguous", "no_match"}
    """
    parts = name_parts_graph(node_name)
    if parts is None:
        return "not_person", []

    last, first, mid = parts

    # Pass 1: DOB on the node
    existing_dob = _u(node_data.get("date_of_birth"))
    if existing_dob:
        key = (last, first, existing_dob)
        recs = index["by_name_dob"].get(key, [])
        if len(recs) == 1:
            return "dob", recs
        if recs:
            return "dob_ambiguous", recs

    # Pass 2: name + address
    name_key = (last, first, mid)
    name_recs = index["by_name"].get(name_key, [])
    if not name_recs:
        # Fast fallback: use the (last, first) index
        name_recs = index["by_name_no_mid"].get((last, first), [])

    if len(name_recs) == 1:
        return "name_unique", name_recs

    if len(name_recs) > 1 and addresses:
        # find voters whose address matches any of the node's addresses
        matched = []
        for rec in name_recs:
            voter_addr = (rec["addr1"], rec["zip"][:5])
            for node_addr in addresses:
                node_street, node_zip = node_addr
                # fuzzy street match: first token + street number
                if _addr_compatible(node_street, voter_addr[0]) and (
                    not node_zip or not voter_addr[1] or node_zip == voter_addr[1]
                ):
                    matched.append(rec)
                    break
        if len(matched) == 1:
            return "address", matched
        if matched:
            return "address_ambiguous", matched

    if len(name_recs) > 1:
        return "name_ambiguous", name_recs
    return "no_match", []


def _addr_compatible(a, b):
    """True if a and b look like the same street address (number + first street word)."""
    ta = a.split()
    tb = b.split()
    if len(ta) < 2 or len(tb) < 2:
        return False
    return ta[0] == tb[0] and ta[1] == tb[1]


def enrich_graph(G, index, pickle_out=None):
    """Attach voter attributes to every owner node that matches uniquely."""
    stats = {"unique": 0, "address": 0, "ambiguous": 0, "no_match": 0, "not_person": 0}
    for node in list(G.nodes):
        if not node.startswith("owner|"):
            continue
        nd = G.nodes[node]
        if nd.get("kind") not in ("person", "trust"):
            continue
        # skip already-enriched
        if nd.get("voter_match") is not None:
            continue
        name = node[6:]
        addresses = _collect_node_addresses(G, node)
        mt, recs = match_node(name, nd, addresses, index)
        if mt == "dob" or mt == "name_unique":
            rec = recs[0]
            nd["voter_id"] = rec["voter_id"]
            nd["date_of_birth"] = rec["dob"]
            nd["residential_address"] = f"{rec['addr1']}, {rec['city']}, {rec['zip']}"
            nd["voter_status"] = rec["status"]
            nd["party_affiliation"] = rec["party"]
            nd["voter_match"] = mt
            stats["unique"] += 1
        elif mt == "address":
            rec = recs[0]
            nd["voter_id"] = rec["voter_id"]
            nd["date_of_birth"] = rec["dob"]
            nd["residential_address"] = f"{rec['addr1']}, {rec['city']}, {rec['zip']}"
            nd["voter_status"] = rec["status"]
            nd["party_affiliation"] = rec["party"]
            nd["voter_match"] = mt
            stats["address"] += 1
        elif mt in ("name_ambiguous", "address_ambiguous", "dob_ambiguous"):
            nd["voter_candidates"] = [
                {"voter_id": r["voter_id"], "dob": r["dob"],
                 "addr": f"{r['addr1']}, {r['zip']}"} for r in recs[:5]
            ]
            nd["voter_match"] = "ambiguous"
            stats["ambiguous"] += 1
        elif mt == "no_match":
            nd["voter_match"] = "no_match"
            stats["no_match"] += 1
        else:
            stats["not_person"] += 1

    if pickle_out:
        pickle.dump(G, open(pickle_out, "wb"))
    return stats


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", default=os.path.expanduser("~/Downloads/CUYAHOGA.txt"), nargs="?")
    ap.add_argument("--graph", default=os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--index-cache", default=os.path.expanduser("~/Desktop/voter_index.pkl"))
    args = ap.parse_args()

    out_path = args.out or args.graph.replace(".pkl", "_with_voters.pkl") if args.write else None

    print(f"loading graph: {args.graph}")
    G = pickle.load(open(args.graph, "rb"))
    print(f"  {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    if os.path.exists(args.index_cache):
        print(f"loading cached voter index: {args.index_cache}")
        index = pickle.load(open(args.index_cache, "rb"))
    else:
        print(f"building voter index from {args.csv}...")
        index = build_voter_index(args.csv)
        pickle.dump(index, open(args.index_cache, "wb"))
        print(f"  cached to {args.index_cache}")

    print("\nrewriting edge-sourced 'male'/'female' attrs isn't part of this pass.")
    print("matching owner nodes against voter file...")
    stats = enrich_graph(G, index, pickle_out=out_path)
    print("\n=== stats ===")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")
    print(f"\ngraph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
    if out_path:
        print(f"written to {out_path}")
    else:
        print("dry run (use --write)")


if __name__ == "__main__":
    main()
