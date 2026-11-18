"""Load NEO CANDO foreclosure data into the OSI graph.

One CSV row = one defendant on one case. Grouping by CASENO yields the
co-defendant sets. PARCEL is used to join back to the existing parcel fabric.
"""
from __future__ import annotations

import argparse
import csv
import os
import pickle
import re
from collections import defaultdict

import networkx as nx


def _u(s: str | None) -> str:
    return "" if s is None else re.sub(r"\s+", " ", str(s)).strip().upper()


def _clean_defendant(raw: str) -> str:
    """Strip ET AL / ET.AL. suffixes. Keep the 'LAST, FIRST' form if present."""
    n = _u(raw)
    n = re.sub(r"\s*,?\s*ET\.?\s*AL\.?\s*$", "", n)
    n = re.sub(r"\s*,\s*$", "", n)
    return n.strip()


def build_owner_index(G: nx.Graph) -> dict[str, str]:
    """One pass over the graph to map normalized owner names to node keys."""
    index = {}
    for n in G.nodes:
        if n.startswith("owner|") and G.nodes[n].get("queryable") is not False:
            index.setdefault(_u(n[6:]), n)
    return index


def build_parcel_index(G: nx.Graph) -> dict[str, str]:
    """Map dash-stripped parcel IDs to graph node keys.

    The graph stores parcels as raw 8-digit strings (parcel|73423003); NEO
    CANDO writes them with dashes (734-23-003). Normalize both sides once.
    """
    index = {}
    for n in G.nodes:
        if n.startswith("parcel|"):
            index.setdefault(n[7:].replace("-", ""), n)
    return index


def load_neocando(
    csv_path: str,
    G: nx.Graph,
    *,
    year_from: int = 2005,
    year_to: int | None = None,
    limit: int | None = None,
) -> dict:
    """Parse the CSV, add case nodes and co_defendant edges to G.

    Returns stats. Mutates G in place.
    """
    owner_index = build_owner_index(G)
    parcel_index = build_parcel_index(G)
    stats = {
        "rows_read": 0,
        "rows_kept": 0,
        "cases_added": 0,
        "defendants_matched": 0,
        "defendants_new": 0,
        "parcels_linked": 0,
        "co_defendant_edges": 0,
        "cases_with_multiple_named_defendants": 0,
    }

    cases: dict[str, dict] = defaultdict(lambda: {"defendants": set(), "parcel": None, "filed": None, "plaintiff": None})

    with open(csv_path, "r", encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            stats["rows_read"] += 1
            if limit and stats["rows_kept"] >= limit:
                break
            try:
                year = int(row.get("YEAR") or 0)
            except ValueError:
                continue
            if year < year_from or (year_to and year > year_to):
                continue
            caseno = (row.get("CASENO") or "").strip()
            defendant_raw = row.get("DEFENDANT") or ""
            if not caseno or not defendant_raw:
                continue
            stats["rows_kept"] += 1

            dname = _clean_defendant(defendant_raw)
            if not dname:
                continue

            c = cases[caseno]
            c["defendants"].add(dname)
            c["filed"] = row.get("FILEDATE")
            c["plaintiff"] = row.get("PLAINTIFF")
            if not c["parcel"] and row.get("PARCEL"):
                c["parcel"] = row["PARCEL"].strip()

    for caseno, c in cases.items():
        case_key = f"case|{caseno}"
        if case_key not in G:
            G.add_node(
                case_key,
                type="case",
                filed=c["filed"],
                plaintiff=c["plaintiff"],
                source="neocando",
                queryable=False,
            )
            stats["cases_added"] += 1

        parcel_key = None
        if c["parcel"]:
            parcel_key = parcel_index.get(c["parcel"].replace("-", ""))
        if parcel_key and parcel_key in G:
            if not G.has_edge(case_key, parcel_key):
                G.add_edge(case_key, parcel_key, relation="foreclosed_on", source="neocando")
                stats["parcels_linked"] += 1

        def_keys = []
        for dname in c["defendants"]:
            key = owner_index.get(dname)
            if key is None:
                key = f"owner|{dname}"
                if key not in G:
                    G.add_node(key, type="owner", kind="person", name=dname,
                               source="neocando", queryable=True)
                    stats["defendants_new"] += 1
                else:
                    stats["defendants_matched"] += 1
            else:
                stats["defendants_matched"] += 1
            if not G.has_edge(key, case_key):
                G.add_edge(key, case_key, relation="defendant_in", source="neocando")

        # Note: NEO CANDO's "ET AL" cases repeat the same named defendant across
        # rows; the additional defendants are anonymous ("other heirs"). This
        # dataset does not provide named co-defendants, so no all-pairs loop.
        # If a future dataset names multiple defendants, add the all-pairs pass
        # back here and emit relation="co_defendant" between distinct names.
        if len(def_keys) > 1:
            stats["cases_with_multiple_named_defendants"] += 1

    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--graph", default=os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"))
    ap.add_argument("--year-from", type=int, default=2005)
    ap.add_argument("--year-to", type=int, default=None)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--write", action="store_true", help="Persist changes back to the pickle")
    args = ap.parse_args()

    G = pickle.load(open(args.graph, "rb"))
    before_nodes, before_edges = G.number_of_nodes(), G.number_of_edges()
    print(f"before: {before_nodes:,} nodes, {before_edges:,} edges")

    stats = load_neocando(
        args.csv, G,
        year_from=args.year_from, year_to=args.year_to, limit=args.limit,
    )
    print("stats:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"after:  {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
    print(f"delta:  +{G.number_of_nodes()-before_nodes:,} nodes, +{G.number_of_edges()-before_edges:,} edges")

    if args.write:
        pickle.dump(G, open(args.graph, "wb"))
        print("written to", args.graph)
    else:
        print("dry run (use --write to save)")
