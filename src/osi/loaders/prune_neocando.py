"""Prune NEOCANDO leaves with loose rule: keep anchored nodes, drop the rest.

A node is anchored if:
  (a) it has at least one edge from a non-neocando source (it was already
      part of the graph before the load), or
  (b) it has degree >= 2 in the current graph.

Applied to fixpoint: removing a node can orphan its neighbors, which then
become prunable on the next pass. Only nodes with source="neocando" are
ever considered for removal; the rest of the graph is untouched.
"""
import argparse
import os
import pickle
import sys


def is_neocando_node(G, n):
    return G.nodes[n].get("source") == "neocando"


def has_external_edge(G, n):
    """True if any edge from n comes from a non-neocando source."""
    for nb in G.neighbors(n):
        data = G[n][nb]
        edge_src = data.get("source")
        if edge_src and "neocando" not in str(edge_src):
            return True
    return False


def should_prune(G, n):
    if not is_neocando_node(G, n):
        return False
    if has_external_edge(G, n):
        return False
    # A case with a parcel link is anchored even if its defendant is a new
    # owner with no other edges. The chain defendant -> case -> parcel is a
    # real property-history fact, not a leaf.
    if n.startswith("case|"):
        if any(nb.startswith("parcel|") for nb in G.neighbors(n)):
            return False
    return G.degree(n) < 2


def prune(G, verbose=True):
    """Return (removed_count, rounds)."""
    total = 0
    rounds = 0
    while True:
        rounds += 1
        to_remove = [n for n in list(G.nodes) if should_prune(G, n)]
        if not to_remove:
            break
        G.remove_nodes_from(to_remove)
        total += len(to_remove)
        if verbose:
            print(f"  round {rounds}: removed {len(to_remove):,}")
    return total, rounds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph",
                    default=os.path.expanduser("~/Desktop/cuyahoga_unified_with_neocando.pkl"))
    ap.add_argument("--out", default=None,
                    help="Output pickle. Defaults to <input>_pruned.pkl")
    ap.add_argument("--in-place", action="store_true",
                    help="Overwrite the input file instead of writing a _pruned copy")
    args = ap.parse_args()

    out_path = args.graph if args.in_place else (
        args.out or args.graph.replace(".pkl", "_pruned.pkl"))

    G = pickle.load(open(args.graph, "rb"))
    before_n, before_e = G.number_of_nodes(), G.number_of_edges()
    neocando_before = sum(1 for n in G.nodes if G.nodes[n].get("source") == "neocando")
    print(f"before: {before_n:,} nodes, {before_e:,} edges")
    print(f"neocando-sourced nodes: {neocando_before:,}")

    removed, rounds = prune(G, verbose=True)

    neocando_after = sum(1 for n in G.nodes if G.nodes[n].get("source") == "neocando")
    print()
    print(f"total removed: {removed:,} in {rounds - 1} productive round(s)")
    print(f"neocando nodes kept: {neocando_after:,} of {neocando_before:,}")
    print(f"after:  {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")
    print(f"delta:  -{before_n - G.number_of_nodes():,} nodes, -{before_e - G.number_of_edges():,} edges")

    pickle.dump(G, open(out_path, "wb"))
    print(f"\nwritten to {out_path}")
    if not args.in_place:
        print(f"original at {args.graph} unchanged")


if __name__ == "__main__":
    main()
