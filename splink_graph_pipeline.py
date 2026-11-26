#!/usr/bin/env python3
"""Production pipeline: Splink entity resolution + NetworkX graph pruning.

This script runs the same entity-resolution rules validated by the golden
dataset test (``tests/golden_dataset_test.py``) over the full Cuyahoga person
table, writes resolved clusters, relabels the ownership-transfer graph with
cluster IDs, prunes dead ends while preserving all cycles, and exports a
GraphML file plus a Splink Cluster Studio dashboard.

Default run
-----------
    .venv/bin/python splink_graph_pipeline.py \
        --input analysis/cuyahoga/data/persons_enriched.parquet \
        --graph-input ~/Desktop/cuyahoga_transfers.pkl \
        --output-dir .

By default the pipeline uses the deterministic comparison priors validated by
the golden test.  On sparse Cuyahoga fields, EM training drives the
Jaro-Winkler levels to zero and the exact-name levels to one, which prevents
legitimate variants such as ``JOHN``/``JOHNATHAN`` from merging.  Pass
``--train`` to estimate p/u with Splink and run EM instead.

After Splink clustering, conflicting records are forced apart: two records in
the same raw cluster are split when both have different DOBs, different voter
IDs, or different middle initials.  Missing values never conflict.  Each
output cluster is labelled ``HIGH`` when at least two of its records share a
DOB or voter ID, and ``LOW`` otherwise (including name-only merges and
singletons).

Smoke run
---------
    .venv/bin/python splink_graph_pipeline.py --limit 5000 --no-dashboard

Outputs (in ``--output-dir``)
-----------------------------
    cuyahoga_resolved_clusters.parquet
    cuyahoga_pruned_graph.graphml
    cuyahoga_cluster_studio.html      (unless --no-dashboard)
    cuyahoga_pipeline_stats.json

The canonical comparison and blocking settings live in
``src/osi/splink_config.py`` and are shared with the golden test.
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd
from tqdm import tqdm

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from osi.splink_config import build_settings  # noqa: E402

DEFAULT_INPUT = _ROOT / "analysis" / "cuyahoga" / "data" / "persons_enriched.parquet"
DEFAULT_GRAPH = Path.home() / "Desktop" / "cuyahoga_transfers.pkl"

# Canonical schema expected by ``osi.splink_config``.
CANONICAL_COLUMNS = (
    "first_name",
    "last_name",
    "middle_initial",
    "dob",
    "address",
    "zip_code",
    "voter_id",
    "full_name",
)

# Source columns accepted for each canonical name.  The first alias that
# exists is used; missing optional fields become empty strings.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "node_id": ("node_id", "person_id", "id", "record_id"),
    "first_name": ("first_name", "forename", "given_name", "first"),
    "last_name": ("last_name", "surname", "family_name", "last"),
    "middle_initial": (
        "middle_initial",
        "middle_name",
        "middle",
        "middle_initial_name",
    ),
    "dob": ("dob", "date_of_birth", "birth_date", "birthdate"),
    "address": (
        "address",
        "residential_address",
        "address_line_1",
        "street_address",
        "mailing_address",
    ),
    "zip_code": ("zip_code", "zip", "zipcode", "postal_code"),
    "voter_id": (
        "voter_id",
        "voter_registration_number",
        "registration_number",
        "voter",
    ),
    "full_name": ("full_name", "name"),
    "source_name": ("source_name", "raw_name", "owner_name"),
}


# ============================================================
# PART 1: SPLINK ENTITY RESOLUTION
# ============================================================


def build_splink_settings():
    """Return the canonical settings shared with the golden dataset test."""
    return build_settings()


def _series_text(df: pd.DataFrame, column: str) -> pd.Series:
    return df[column].astype("string").fillna("").str.strip()


def prepare_persons(
    df: pd.DataFrame,
    *,
    limit: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Normalize source columns into the canonical Splink schema.

    Returns the prepared frame (one row per input record, with ``unique_id``)
    and a dict of loading statistics.  ``node_id`` is retained for reporting
    but never registered with Splink.
    """
    stats: dict[str, Any] = {"input_rows": int(len(df))}
    if limit is not None:
        df = df.head(limit).copy()
        stats["limited_to"] = int(limit)

    df = df.copy()
    df.columns = [str(column).strip().lower() for column in df.columns]

    renamed: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical in df.columns:
            renamed[canonical] = canonical
            continue
        match = next((alias for alias in aliases if alias in df.columns), None)
        if match is not None:
            renamed[match] = canonical

    df = df.rename(columns=renamed)

    if "first_name" not in df.columns or "last_name" not in df.columns:
        raise ValueError(
            "input must contain first/last name columns; "
            f"found {sorted(df.columns)}"
        )

    if "node_id" not in df.columns:
        df["node_id"] = [str(index) for index in range(len(df))]

    for column in CANONICAL_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    if "source_name" not in df.columns:
        df["source_name"] = ""

    for column in (
        "first_name",
        "last_name",
        "middle_initial",
        "address",
        "voter_id",
    ):
        df[column] = _series_text(df, column).str.upper()

    # Node IDs are join keys into the ownership graph; preserve their case.
    df["node_id"] = _series_text(df, "node_id")
    df["source_name"] = _series_text(df, "source_name")

    df["middle_initial"] = (
        df["middle_initial"].str.extract(r"([A-Z])", expand=False).fillna("")
    )

    # ZIP codes: keep the first five digits of any postal value.
    zip_text = _series_text(df, "zip_code")
    df["zip_code"] = zip_text.str.extract(r"(\d{5})", expand=False).fillna("")

    # DOB: normalize to ISO strings so DateOfBirthComparison can parse them.
    dob_text = _series_text(df, "dob")
    parsed_dob = pd.to_datetime(
        dob_text.replace("", pd.NA), errors="coerce", format="mixed"
    )
    df["dob"] = parsed_dob.dt.strftime("%Y-%m-%d").fillna("")

    df["full_name"] = (
        df["first_name"].fillna("") + " " + df["last_name"].fillna("")
    ).str.strip()

    blank_names = (df["first_name"] == "") & (df["last_name"] == "")
    stats["dropped_blank_names"] = int(blank_names.sum())
    df = df.loc[~blank_names].reset_index(drop=True)
    stats["prepared_rows"] = int(len(df))
    stats["duplicate_node_ids"] = int(df["node_id"].duplicated().sum())

    for column in CANONICAL_COLUMNS:
        non_blank = int((df[column] != "").sum())
        stats[f"non_blank_{column}"] = non_blank

    df["unique_id"] = range(len(df))
    return df, stats


def build_working_frame(persons: pd.DataFrame) -> pd.DataFrame:
    """Select the Splink columns and turn blank strings into SQL NULLs.

    Blank strings are missing values, not matching values.  If left as "",
    every record with a missing address/ZIP/voter ID would exact-match every
    other record with the same missing field, producing enormous false
    clusters.  SQL NULL comparisons do not contribute match evidence.
    """
    working = persons.loc[:, ["unique_id", *CANONICAL_COLUMNS]].copy()
    for column in CANONICAL_COLUMNS:
        working[column] = working[column].where(working[column] != "", None)
    return working


def run_splink_resolution(
    persons: pd.DataFrame,
    *,
    threshold: float = 0.95,
    train: bool = True,
    em_passes: int = 2,
    seed: int | None = 42,
    progress: bool = True,
):
    """Train, predict, and cluster with Splink.

    Returns ``(linker, pairwise_predictions, clusters)`` as Splink dataframes.
    The caller converts the clustered frame to pandas when needed.
    """
    from splink import Linker, block_on
    from splink.internals.duckdb.database_api import DuckDBAPI

    working = build_working_frame(persons)

    db_api = DuckDBAPI()
    df_sdf = db_api.register(working, table_name="persons")
    linker = Linker(df_sdf, build_splink_settings(), log_level=None)

    em_rules = [
        block_on("dob"),
        block_on("address"),
        block_on("last_name", "first_name"),
    ]

    if train:
        # Probability two random records match.  A common-name blocking rule
        # is a reasonable high-recall deterministic match proxy here.
        try:
            linker.training.estimate_probability_two_random_records_match(
                [block_on("last_name", "first_name")],
                recall=0.7,
            )
        except Exception as exc:  # pragma: no cover - backend/data dependent
            tqdm.write(f"WARNING: probability estimate failed: {exc}")

        try:
            linker.training.estimate_u_using_random_sampling(
                max_pairs=1_000_000, seed=seed
            )
        except Exception as exc:  # pragma: no cover - backend/data dependent
            tqdm.write(f"WARNING: u-probability estimate failed: {exc}")

        # Each EM pass excludes comparisons that use its blocking columns.
        # DOB and address are highly selective here and keep the pair count
        # tractable while jointly covering every comparison.
        for pass_number, rule in enumerate(em_rules[: max(0, em_passes)], start=1):
            total_iterations = 20
            with tqdm(
                total=total_iterations,
                desc=f"EM pass {pass_number}",
                unit="iter",
                leave=False,
                disable=not progress,
            ) as em_bar:
                handler = _EMIterationHandler(em_bar)
                em_logger = logging.getLogger("splink")
                em_logger.addHandler(handler)
                old_level = em_logger.level
                em_logger.setLevel(logging.INFO)
                try:
                    linker.training.estimate_parameters_using_expectation_maximisation(
                        rule
                    )
                except Exception as exc:  # pragma: no cover - data dependent
                    tqdm.write(
                        f"WARNING: EM pass {pass_number} failed: {exc}"
                    )
                finally:
                    em_logger.removeHandler(handler)
                    em_logger.setLevel(old_level)

    pairwise_predictions = linker.inference.predict(
        threshold_match_probability=threshold
    )
    clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(
        pairwise_predictions, threshold_match_probability=threshold
    )
    return linker, pairwise_predictions, clusters


class _EMIterationHandler(logging.Handler):
    """Advance a tqdm bar when Splink logs an EM iteration."""

    def __init__(self, bar: tqdm):
        super().__init__()
        self.bar = bar

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.getMessage().lstrip().startswith("Iteration"):
                self.bar.update(1)
        except Exception:  # pragma: no cover - defensive
            pass


# ============================================================
# PART 1B: CONFLICT SPLITTING AND CLUSTER CONFIDENCE
# ============================================================


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def _date_key(value: Any) -> str:
    if _is_blank(value):
        return ""
    return str(value).strip()[:10]


def _middle_key(value: Any) -> str:
    if _is_blank(value):
        return ""
    text = str(value).strip().upper()
    return text[:1] if text[:1].isalpha() else ""


def _name_key(value: Any) -> str:
    """Normalize a name for comparison without changing initials."""
    if _is_blank(value):
        return ""
    text = str(value).strip().upper()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _first_names_compatible(left: pd.Series, right: pd.Series) -> bool:
    """Treat equal names and common prefix variants as the same first name.

    ``JOHN``/``JOHNATHAN`` and ``CHRIS``/``CHRISTOPHER`` are variants, while
    ``ANTONIO``/``FELIX`` and ``DORELA``/``ERMIRA`` are not.  Missing first
    names do not conflict.
    """
    left_name = _name_key(left.get("first_name"))
    right_name = _name_key(right.get("first_name"))
    if not left_name or not right_name:
        return True
    if left_name == right_name:
        return True
    return left_name.startswith(right_name) or right_name.startswith(left_name)


def _is_ghost_record(record: pd.Series) -> bool:
    """No DOB, address, middle initial, or voter ID means no link evidence."""
    return all(
        _is_blank(record.get(column))
        for column in ("dob", "address", "middle_initial", "voter_id")
    )


def _identifier_conflict(left: pd.Series, right: pd.Series) -> str | None:
    """Return the conflicting identifier type for two records, if any.

    Missing values never conflict.  Middle names are compared by initial so
    ``ELLEN`` and ``E`` are the same identifier.  Different first names with
    the same last name conflict unless the pair shares an exact DOB or voter
    ID.
    """
    left_dob = _date_key(left.get("dob"))
    right_dob = _date_key(right.get("dob"))
    if left_dob and right_dob and left_dob != right_dob:
        return "dob"

    left_voter = (
        "" if _is_blank(left.get("voter_id")) else str(left.get("voter_id"))
    )
    right_voter = (
        "" if _is_blank(right.get("voter_id")) else str(right.get("voter_id"))
    )
    left_voter = left_voter.strip().upper()
    right_voter = right_voter.strip().upper()
    if left_voter and right_voter and left_voter != right_voter:
        return "voter_id"

    left_middle = _middle_key(left.get("middle_initial"))
    right_middle = _middle_key(right.get("middle_initial"))
    if left_middle and right_middle and left_middle != right_middle:
        return "middle_initial"

    left_last = _name_key(left.get("last_name"))
    right_last = _name_key(right.get("last_name"))
    if (
        left_last
        and right_last
        and left_last == right_last
        and not _first_names_compatible(left, right)
    ):
        same_dob = bool(left_dob and right_dob and left_dob == right_dob)
        same_voter = bool(
            left_voter and right_voter and left_voter == right_voter
        )
        if not (same_dob or same_voter):
            return "first_name"
    return None


def _partition_conflicting_group(records: list[pd.Series]) -> list[list[int]]:
    """Partition record positions so no group contains a conflict pair.

    Records are assigned in most-conflicted-first order and placed in the
    first group where every existing member is compatible.  This is a greedy
    graph colouring of the conflict graph; it guarantees that no conflicting
    pair shares a final cluster.
    """
    if len(records) <= 1:
        return [list(range(len(records)))]

    conflict_counts = [0] * len(records)
    for left in range(len(records)):
        for right in range(left + 1, len(records)):
            if _identifier_conflict(records[left], records[right]):
                conflict_counts[left] += 1
                conflict_counts[right] += 1

    order = sorted(
        range(len(records)),
        key=lambda index: (-conflict_counts[index], index),
    )
    groups: list[list[int]] = []
    for index in order:
        for group in groups:
            if all(
                _identifier_conflict(records[index], records[other]) is None
                for other in group
            ):
                group.append(index)
                break
        else:
            groups.append([index])

    # Put the largest group first so it can retain the original cluster ID.
    groups.sort(key=lambda group: (-len(group), min(group)))
    return groups


def _clusters_with_shared_identifier(
    frame: pd.DataFrame,
    column: str,
    cluster_column: str,
) -> set[Any]:
    """Cluster IDs where at least two records share a non-blank value."""
    values = frame[column].astype("string").fillna("").str.strip()
    if column == "voter_id":
        values = values.str.upper()
    else:
        values = values.str.slice(0, 10)
    subset = frame.loc[values != ""].copy()
    if subset.empty:
        return set()
    subset[column] = values.loc[subset.index]
    counts = subset.groupby([cluster_column, column], dropna=False).size()
    shared = counts[counts >= 2].index.get_level_values(0)
    return set(shared.tolist())


def split_conflicting_clusters(
    clustered: pd.DataFrame,
    *,
    cluster_column: str = "cluster_id",
    node_column: str = "node_id",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Split Splink clusters when records carry conflicting identifiers.

    A pair conflicts when both records have a DOB and the DOBs differ, both
    have a voter ID and the IDs differ, or both have a middle initial and the
    initials differ.  Records that share a last name but have fundamentally
    different first names also conflict unless they share an exact DOB or
    voter ID.  Missing values never conflict.

    A ghost record has no DOB, address, middle initial, or voter ID.  Ghosts
    are forced into singleton clusters because a name match alone is not
    evidence that two ghost records are the same person.

    Conflict checks apply to every pair inside a raw Splink cluster, and a
    valid partition is built so no final cluster contains a conflicting pair
    even when the pair is only connected through a compatible third record.
    The largest subgroup keeps the original cluster ID; additional subgroups
    receive new IDs after the current maximum.  Every row receives a
    ``confidence_level``: ``HIGH`` when at least two cluster members share a
    DOB or voter ID, ``LOW`` otherwise.
    """
    required = {"unique_id", cluster_column}
    missing = required - set(clustered.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")

    result = clustered.copy()
    if node_column not in result.columns:
        result[node_column] = result["unique_id"].astype(str)

    numeric_ids = pd.api.types.is_numeric_dtype(result[cluster_column])
    raw_max = (
        int(result[cluster_column].max()) if numeric_ids and len(result) else 0
    )
    next_id = raw_max + 1

    refined_ids: dict[Any, Any] = {}
    split_clusters = 0
    records_resplit = 0
    ghost_records = 0
    ghost_records_split = 0
    conflict_counts: Counter[str] = Counter()
    raw_cluster_count = int(result[cluster_column].nunique())

    for raw_id, group in result.groupby(cluster_column, sort=False):
        records = [row for _, row in group.iterrows()]
        ghost_positions = [
            position
            for position, record in enumerate(records)
            if _is_ghost_record(record)
        ]
        ghost_position_set = set(ghost_positions)
        normal_positions = [
            position
            for position in range(len(records))
            if position not in ghost_position_set
        ]
        ghost_records += len(ghost_positions)

        if len(records) <= 1:
            refined_ids[records[0]["unique_id"]] = raw_id
            continue

        # Count each conflicting pair once for auditability.  Ghosts are
        # excluded because they are always isolated.
        for left_index, left_position in enumerate(normal_positions):
            for right_position in normal_positions[left_index + 1 :]:
                reason = _identifier_conflict(
                    records[left_position], records[right_position]
                )
                if reason:
                    conflict_counts[reason] += 1

        if normal_positions:
            normal_records = [records[position] for position in normal_positions]
            normal_groups = _partition_conflicting_group(normal_records)
            groups = [
                [normal_positions[position] for position in group_positions]
                for group_positions in normal_groups
            ]
        else:
            groups = []
        # Every ghost is its own group, even when another ghost is present.
        groups.extend([[position] for position in ghost_positions])

        if len(groups) == 1:
            for record in records:
                refined_ids[record["unique_id"]] = raw_id
            continue

        split_clusters += 1
        for group_number, positions in enumerate(groups):
            if group_number == 0:
                assigned_id = raw_id
            elif numeric_ids:
                assigned_id = next_id
                next_id += 1
            else:
                assigned_id = f"{raw_id}__split{group_number}"
            for position in positions:
                refined_ids[records[position]["unique_id"]] = assigned_id
                if group_number > 0 and position in ghost_position_set:
                    ghost_records_split += 1
            if group_number > 0:
                records_resplit += len(positions)

    result["splink_cluster_id"] = result[cluster_column]
    result[cluster_column] = result["unique_id"].map(refined_ids)
    if result[cluster_column].isna().any():
        raise ValueError("some records were not assigned a refined cluster ID")

    shared_dob = _clusters_with_shared_identifier(
        result, "dob", cluster_column
    )
    shared_voter = _clusters_with_shared_identifier(
        result, "voter_id", cluster_column
    )
    cluster_sizes = result.groupby(cluster_column).size()
    high_ids = {
        cluster_id
        for cluster_id in cluster_sizes.index
        if cluster_sizes[cluster_id] > 1
        and (cluster_id in shared_dob or cluster_id in shared_voter)
    }
    result["confidence_level"] = result[cluster_column].map(
        lambda cluster_id: "HIGH" if cluster_id in high_ids else "LOW"
    )

    per_cluster = result.groupby(cluster_column)["confidence_level"].first()
    stats = {
        "raw_clusters": raw_cluster_count,
        "refined_clusters": int(result[cluster_column].nunique()),
        "split_clusters": int(split_clusters),
        "split_off_clusters": int(
            result[cluster_column].nunique() - raw_cluster_count
        ),
        "records_resplit": int(records_resplit),
        "ghost_records": int(ghost_records),
        "ghost_records_split": int(ghost_records_split),
        "conflicts": dict(conflict_counts),
        "high_confidence_clusters": int((per_cluster == "HIGH").sum()),
        "low_confidence_clusters": int((per_cluster == "LOW").sum()),
        "high_confidence_records": int(
            (result["confidence_level"] == "HIGH").sum()
        ),
        "low_confidence_records": int(
            (result["confidence_level"] == "LOW").sum()
        ),
    }
    return result, stats


# ============================================================
# PART 2: GRAPH PRUNING - PRESERVE CYCLICAL CHAINS
# ============================================================


def prune_graph_preserve_chains(
    graph: nx.DiGraph,
    *,
    progress: bool = True,
) -> tuple[nx.DiGraph, dict[str, Any]]:
    """Keep all cycles plus the paths from the main component that reach them.

    The ownership-transfer graph is directed.  A cycle is a strongly connected
    component with more than one node, or a single node with a self-loop.
    Nodes in the largest weakly connected component that can reach any cycle
    are kept; every other node (dead ends, acyclic tails, isolated records) is
    dropped.
    """
    if not isinstance(graph, nx.DiGraph):
        raise TypeError("prune_graph_preserve_chains requires a directed graph")

    stats: dict[str, Any] = {
        "original_nodes": int(graph.number_of_nodes()),
        "original_edges": int(graph.number_of_edges()),
    }
    if graph.number_of_nodes() == 0:
        stats.update(
            {
                "main_component_nodes": 0,
                "cycles": 0,
                "cycle_nodes": 0,
                "path_nodes": 0,
                "pruned_nodes": 0,
                "pruned_edges": 0,
                "removed_nodes": 0,
            }
        )
        return graph.copy(), stats

    # Largest weakly connected component.
    wccs = nx.weakly_connected_components(graph)
    main_cc_nodes = max(wccs, key=len)
    main_cc_set = set(main_cc_nodes)
    stats["main_component_nodes"] = len(main_cc_set)

    # All cycles, including cycles disconnected from the main component.
    sccs = nx.strongly_connected_components(graph)
    cycle_nodes: set[Any] = set()
    cycle_count = 0
    for scc in sccs:
        if len(scc) > 1:
            cycle_nodes.update(scc)
            cycle_count += 1
        else:
            node = next(iter(scc))
            if graph.has_edge(node, node):
                cycle_nodes.add(node)
                cycle_count += 1
    stats["cycles"] = cycle_count
    stats["cycle_nodes"] = len(cycle_nodes)

    # Reverse BFS from cycle nodes in the main component finds every node
    # that can reach a cycle.  ``reverse(copy=False)`` avoids copying the graph.
    reverse = graph.reverse(copy=False)
    dist: dict[Any, int] = {}
    queue: list[Any] = []
    for node in cycle_nodes & main_cc_set:
        dist[node] = 0
        queue.append(node)

    head = 0
    while head < len(queue):
        node = queue[head]
        head += 1
        for predecessor in reverse.successors(node):
            if predecessor in main_cc_set and predecessor not in dist:
                dist[predecessor] = dist[node] + 1
                queue.append(predecessor)

    path_nodes = set(dist)
    stats["path_nodes"] = len(path_nodes)

    keep_nodes = cycle_nodes | path_nodes
    pruned = graph.subgraph(keep_nodes).copy()
    stats["pruned_nodes"] = int(pruned.number_of_nodes())
    stats["pruned_edges"] = int(pruned.number_of_edges())
    stats["removed_nodes"] = stats["original_nodes"] - stats["pruned_nodes"]
    return pruned, stats


# ============================================================
# PART 3: CLUSTER GRAPH BUILD
# ============================================================


def build_cluster_graph(
    graph: nx.DiGraph,
    node_to_cluster: dict[str, str],
    *,
    cluster_labels: dict[str, str] | None = None,
    cluster_confidences: dict[str, str] | None = None,
    only_resolved: bool = False,
) -> tuple[nx.DiGraph, dict[str, Any]]:
    """Relabel owners and collapse edges without double-counting source deeds.

    New transfer graphs carry one provenance record per source transaction.
    When several owner aliases collapse into one cluster pair, transaction IDs
    deduplicate joint-party expansions.  Legacy graphs remain readable, but
    their counts are aggregate estimates and are flagged in the returned stats.
    Unresolved endpoints keep their original IDs unless ``only_resolved`` is
    explicitly enabled.
    """
    cluster_labels = cluster_labels or {}
    cluster_confidences = cluster_confidences or {}
    cluster_sizes = Counter(node_to_cluster.values())
    resolved_input_nodes = sum(
        str(node) in node_to_cluster for node in graph.nodes()
    )
    stats: dict[str, Any] = {
        "input_nodes": int(graph.number_of_nodes()),
        "input_edges": int(graph.number_of_edges()),
        "resolution_mappings": len(node_to_cluster),
        "resolved_nodes": int(resolved_input_nodes),
        "unresolved_input_nodes": int(
            graph.number_of_nodes() - resolved_input_nodes
        ),
        "collapsed_self_loops": 0,
        "dropped_edges": 0,
        "legacy_edges_without_transaction_ids": 0,
    }

    mapped: dict[str, str] = {}
    for node in graph.nodes():
        cluster_id = node_to_cluster.get(str(node))
        mapped[node] = (
            str(node) if cluster_id is None else f"cluster:{cluster_id}"
        )

    out = nx.DiGraph()
    transactions_by_edge: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)

    def ensure_node(original: str, mapped_id: str) -> None:
        if mapped_id in out:
            return
        cluster_id = node_to_cluster.get(str(original))
        if cluster_id is None:
            kind, _, _ = str(original).partition("|")
            out.add_node(
                mapped_id,
                label=str(original),
                resolved=False,
                cluster_size=0,
                kind=kind or "owner",
            )
        else:
            out.add_node(
                mapped_id,
                label=cluster_labels.get(cluster_id, mapped_id),
                resolved=True,
                cluster_size=int(cluster_sizes.get(cluster_id, 0)),
                confidence_level=str(cluster_confidences.get(cluster_id, "")),
                kind="person_cluster",
            )

    def ensure_edge(source: str, target: str, relation: str):
        key = (source, target)
        if key not in transactions_by_edge:
            transactions_by_edge[key] = {}
            out.add_edge(
                source,
                target,
                weight=0.0,
                party_pair_weight=0.0,
                total_amount=0.0,
                n_transactions=0.0,
                first_date="",
                last_date="",
                book_pages=[],
                transactions=[],
                relation=relation,
            )
        return out[source][target]

    for source, target, attrs in graph.edges(data=True):
        source_mapped = mapped[source]
        target_mapped = mapped[target]
        if only_resolved and (
            node_to_cluster.get(str(source)) is None
            and node_to_cluster.get(str(target)) is None
        ):
            stats["dropped_edges"] += 1
            continue

        ensure_node(source, source_mapped)
        ensure_node(target, target_mapped)
        if source_mapped == target_mapped:
            stats["collapsed_self_loops"] += 1

        key = (source_mapped, target_mapped)
        relation = _as_text(attrs.get("relation")) or "transfer"
        edge = ensure_edge(source_mapped, target_mapped, relation)
        weight = _as_float(attrs.get("weight"), default=1.0)
        edge["party_pair_weight"] += weight

        raw_transactions = attrs.get("transactions")
        has_transaction_ids = (
            isinstance(raw_transactions, (list, tuple))
            and bool(raw_transactions)
            and all(
                isinstance(item, dict) and _as_text(item.get("transaction_id"))
                for item in raw_transactions
            )
        )
        if has_transaction_ids:
            for item in raw_transactions:
                transaction_id = _as_text(item["transaction_id"])
                transactions_by_edge[key].setdefault(transaction_id, dict(item))
            continue

        stats["legacy_edges_without_transaction_ids"] += 1
        legacy_count = _as_float(
            attrs.get("n_transactions"),
            default=weight,
        )
        edge["weight"] += weight
        edge["n_transactions"] += legacy_count
        edge["total_amount"] += _as_float(
            attrs.get("total_amount"), default=0.0
        )
        first_date = _as_text(attrs.get("first_date"))
        last_date = _as_text(attrs.get("last_date"))
        if first_date and (
            not edge["first_date"] or first_date < edge["first_date"]
        ):
            edge["first_date"] = first_date
        if last_date and last_date > edge["last_date"]:
            edge["last_date"] = last_date
        book_pages = attrs.get("book_pages") or []
        if isinstance(book_pages, (list, tuple)):
            edge["book_pages"].extend(_as_text(value) for value in book_pages)
        elif book_pages:
            edge["book_pages"].append(_as_text(book_pages))

    for (source, target), transactions in transactions_by_edge.items():
        if not transactions:
            continue
        edge = out[source][target]
        ordered = [transactions[key] for key in sorted(transactions)]
        edge["transactions"] = ordered
        edge["weight"] += len(ordered)
        edge["n_transactions"] += len(ordered)
        edge["total_amount"] += sum(
            _as_float(item.get("amount"), default=0.0) for item in ordered
        )
        dates = [
            _as_text(item.get("date"))
            for item in ordered
            if _as_text(item.get("date"))
        ]
        if dates:
            if not edge["first_date"]:
                edge["first_date"] = min(dates)
            else:
                edge["first_date"] = min(edge["first_date"], min(dates))
            edge["last_date"] = max(edge["last_date"], max(dates))
        edge["book_pages"].extend(
            _as_text(item["book_page"])
            for item in ordered
            if _as_text(item.get("book_page"))
        )

    stats["transaction_provenance_complete"] = (
        stats["legacy_edges_without_transaction_ids"] == 0
    )
    stats["output_nodes"] = int(out.number_of_nodes())
    stats["output_edges"] = int(out.number_of_edges())
    return out, stats


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


# ============================================================
# PART 4: GRAPHML EXPORT
# ============================================================


def _graphml_value(value: Any) -> Any:
    """Convert a NetworkX attribute into a GraphML-safe scalar."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, (list, tuple, set)):
        return json.dumps(list(value), default=str)
    if isinstance(value, dict):
        return json.dumps(value, default=str, sort_keys=True)
    return str(value)


def sanitize_graph(graph: nx.Graph) -> nx.Graph:
    """Return a copy whose node/edge attributes are GraphML-safe."""
    sanitized = graph.copy()
    for _, data in sanitized.nodes(data=True):
        for key in list(data):
            data[key] = _graphml_value(data[key])
    for _, _, data in sanitized.edges(data=True):
        for key in list(data):
            data[key] = _graphml_value(data[key])
    return sanitized


def write_graphml(graph: nx.Graph, path: Path) -> dict[str, int]:
    """Write GraphML and validate its node/edge counts without re-loading it."""
    from lxml import etree

    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_graph(graph)
    nx.write_graphml_lxml(
        sanitized,
        str(path),
        encoding="utf-8",
        prettyprint=False,
    )

    node_count = 0
    edge_count = 0
    for _, element in etree.iterparse(str(path), events=("end",)):
        tag = etree.QName(element).localname
        if tag == "node":
            node_count += 1
            element.clear()
        elif tag == "edge":
            edge_count += 1
            element.clear()
    return {"graphml_nodes": node_count, "graphml_edges": edge_count}


# ============================================================
# PART 5: AUDIT AND OUTPUT
# ============================================================


def cluster_audit(
    clustered: pd.DataFrame,
    *,
    cluster_column: str = "cluster_id",
    node_column: str = "node_id",
    top_n: int = 10,
) -> dict[str, Any]:
    """Summarize cluster sizes and return the largest clusters."""
    sizes = (
        clustered.groupby(cluster_column, dropna=False)
        .size()
        .sort_values(ascending=False)
    )
    multi = sizes[sizes > 1]

    confidences: dict[Any, str] = {}
    if "confidence_level" in clustered.columns:
        confidences = (
            clustered.drop_duplicates(cluster_column)
            .set_index(cluster_column)["confidence_level"]
            .to_dict()
        )

    top: list[dict[str, Any]] = []
    if len(sizes):
        wanted = list(sizes.head(top_n).index)
        members = (
            clustered.loc[clustered[cluster_column].isin(wanted)]
            .groupby(cluster_column)[node_column]
            .apply(list)
            .to_dict()
        )
        for cluster_id in wanted:
            entry = {
                "cluster_id": str(cluster_id),
                "size": int(sizes[cluster_id]),
                "node_ids": [str(node) for node in members.get(cluster_id, [])],
            }
            if cluster_id in confidences:
                entry["confidence_level"] = str(confidences[cluster_id])
            top.append(entry)

    audit: dict[str, Any] = {
        "total_records": int(len(clustered)),
        "total_clusters": int(sizes.size),
        "multi_record_clusters": int(len(multi)),
        "records_in_multi_clusters": int(multi.sum()),
        "singleton_clusters": int((sizes == 1).sum()),
        "largest_cluster_size": int(sizes.iloc[0]) if len(sizes) else 0,
        "top_clusters": top,
    }
    if confidences:
        multi_ids = set(multi.index)
        multi_high = sum(
            1
            for cluster_id in multi_ids
            if str(confidences.get(cluster_id, "")).upper() == "HIGH"
        )
        audit["confidence"] = {
            "high_clusters": int(
                sum(
                    1
                    for cluster_id in sizes.index
                    if str(confidences.get(cluster_id, "")).upper() == "HIGH"
                )
            ),
            "low_clusters": int(
                sum(
                    1
                    for cluster_id in sizes.index
                    if str(confidences.get(cluster_id, "")).upper() == "LOW"
                )
            ),
            "high_multi_record_clusters": int(multi_high),
            "low_multi_record_clusters": int(len(multi) - multi_high),
            "high_records": int(
                (clustered["confidence_level"].astype(str).str.upper() == "HIGH").sum()
            ),
            "low_records": int(
                (clustered["confidence_level"].astype(str).str.upper() == "LOW").sum()
            ),
        }
    return audit


def print_audit(audit: dict[str, Any], *, max_nodes_per_cluster: int = 25) -> None:
    line = "=" * 60
    print(f"\n{line}")
    print("ENTITY RESOLUTION AUDIT")
    print(line)
    print(f"Total records processed:     {audit['total_records']:,}")
    print(f"Total clusters:              {audit['total_clusters']:,}")
    print(f"Multi-record clusters:       {audit['multi_record_clusters']:,}")
    print(f"Records in multi clusters:   {audit['records_in_multi_clusters']:,}")
    print(f"Singleton clusters:          {audit['singleton_clusters']:,}")
    print(f"Largest cluster size:        {audit['largest_cluster_size']:,}")
    confidence = audit.get("confidence")
    if confidence:
        print(
            f"High-confidence clusters:    {confidence['high_clusters']:,} "
            f"({confidence['high_multi_record_clusters']:,} multi-record)"
        )
        print(
            f"Low-confidence clusters:     {confidence['low_clusters']:,} "
            f"({confidence['low_multi_record_clusters']:,} multi-record)"
        )
    print("\nTop 10 largest clusters:")
    for rank, cluster in enumerate(audit["top_clusters"], start=1):
        nodes = cluster["node_ids"]
        shown = ", ".join(nodes[:max_nodes_per_cluster])
        if len(nodes) > max_nodes_per_cluster:
            shown += f", ... (+{len(nodes) - max_nodes_per_cluster:,} more)"
        level = cluster.get("confidence_level", "?")
        print(
            f"  {rank:>2}. cluster_id={cluster['cluster_id']:<12} "
            f"size={cluster['size']:<4} confidence={level:<5} nodes: {shown}"
        )
    print(line)


def write_cluster_parquet(
    persons: pd.DataFrame,
    clusters: pd.DataFrame,
    *,
    path: Path,
) -> pd.DataFrame:
    """Merge cluster IDs back onto the original person rows."""
    cluster_columns = ["unique_id", "cluster_id"]
    for optional in ("splink_cluster_id", "confidence_level"):
        if optional in clusters.columns:
            cluster_columns.append(optional)
    merged = persons.merge(
        clusters[cluster_columns],
        on="unique_id",
        how="left",
        validate="one_to_one",
    )
    sizes = merged.groupby("cluster_id")["unique_id"].transform("size")
    merged["cluster_size"] = sizes.astype("int64")

    preferred = [
        "node_id",
        "unique_id",
        "cluster_id",
        "cluster_size",
        "splink_cluster_id",
        "confidence_level",
        "first_name",
        "last_name",
        "middle_initial",
        "suffix",
        "dob",
        "address",
        "zip_code",
        "voter_id",
        "full_name",
        "source_name",
    ]
    ordered = [column for column in preferred if column in merged.columns]
    ordered += [column for column in merged.columns if column not in ordered]
    merged = merged.loc[:, ordered]

    path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(path, index=False, compression="zstd")
    return merged


def load_graph(path: Path | None, *, demo: bool = False) -> nx.DiGraph:
    if demo:
        print("Explicit --demo requested; using the built-in sample graph.")
        return create_sample_graph()
    if path is None:
        raise ValueError("graph input is required unless --demo is explicitly set")
    if not path.exists():
        raise FileNotFoundError(f"graph input not found: {path}")
    if path.suffix.lower() in {".pkl", ".pickle"}:
        with path.open("rb") as handle:
            graph = pickle.load(handle)
    elif path.suffix.lower() == ".graphml":
        graph = nx.read_graphml(path)
    elif path.suffix.lower() == ".gexf":
        graph = nx.read_gexf(path)
    else:
        raise ValueError(f"unsupported graph format: {path.suffix}")
    if not isinstance(graph, nx.DiGraph):
        raise TypeError(
            "pruning requires a directed graph; "
            f"{path} loaded as {type(graph).__name__}"
        )
    return graph


def create_sample_graph() -> nx.DiGraph:
    """Create a sample graph with cycles and chains for smoke tests."""
    graph = nx.DiGraph()
    graph.add_edge("A", "B")
    graph.add_edge("B", "C")
    graph.add_edge("C", "D")
    graph.add_edge("C", "A")
    graph.add_edge("E", "F")
    graph.add_edge("F", "G")
    graph.add_edge("G", "E")
    graph.add_edge("D", "H")
    graph.add_edge("H", "E")
    graph.add_edge("D", "X")
    graph.add_edge("X", "Y")
    graph.add_edge("Y", "Z")
    graph.add_edge("A", "P")
    graph.add_edge("P", "Q")
    return graph


# ============================================================
# MAIN PIPELINE
# ============================================================


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    progress = not args.quiet

    cluster_path = output_dir / "cuyahoga_resolved_clusters.parquet"
    graphml_path = output_dir / "cuyahoga_pruned_graph.graphml"
    dashboard_path = output_dir / "cuyahoga_cluster_studio.html"
    stats_path = output_dir / "cuyahoga_pipeline_stats.json"

    stages = [
        "load parquet",
        "prepare",
        "train",
        "predict",
        "cluster",
        "split conflicts",
        "write clusters",
        "load graph",
        "relabel graph",
        "prune graph",
        "write graphml",
        "dashboard",
        "audit",
    ]
    bar = tqdm(
        total=len(stages),
        desc="Pipeline",
        unit="stage",
        disable=not progress,
    )

    def stage(name: str) -> None:
        bar.set_description(f"Pipeline: {name}")
        bar.update(1)

    stage("load parquet")
    input_path = Path(args.input).expanduser()
    if not input_path.exists():
        raise FileNotFoundError(f"input not found: {input_path}")
    source = pd.read_parquet(input_path)
    tqdm.write(f"Loaded {input_path} ({len(source):,} rows)")

    stage("prepare")
    persons, load_stats = prepare_persons(source, limit=args.limit)
    tqdm.write(
        f"Prepared {load_stats['prepared_rows']:,} rows "
        f"({load_stats['dropped_blank_names']:,} blank names dropped)"
    )

    stage("train")
    train_started = time.time()
    training_enabled = bool(args.train) and not bool(args.no_training)
    if training_enabled:
        tqdm.write("Training enabled: estimating p/u and running EM passes")
    else:
        tqdm.write("Training disabled: using the deterministic golden priors")
    linker, pairwise, clusters_sdf = run_splink_resolution(
        persons,
        threshold=args.threshold,
        train=training_enabled,
        em_passes=args.em_passes,
        seed=args.seed,
        progress=progress,
    )
    training_seconds = time.time() - train_started
    tqdm.write(f"Training finished in {training_seconds:.1f}s")

    stage("predict")
    tqdm.write(f"Predicting pairs at match probability >= {args.threshold}")
    clusters = clusters_sdf.as_pandas_dataframe()
    pairwise_count = pairwise.as_pandas_dataframe().shape[0]
    tqdm.write(f"Pairwise matches: {pairwise_count:,}")

    stage("cluster")
    tqdm.write(
        f"Clustered {len(clusters):,} records into "
        f"{clusters['cluster_id'].nunique():,} clusters"
    )

    stage("split conflicts")
    # Splink's clustered frame normally carries the input columns, but merge
    # any missing identifier columns defensively.
    identifier_columns = ["unique_id", "middle_initial", "dob", "voter_id"]
    missing_identifiers = [
        column for column in identifier_columns if column not in clusters.columns
    ]
    clusters_for_split = clusters
    if missing_identifiers:
        clusters_for_split = clusters.merge(
            persons[missing_identifiers],
            on="unique_id",
            how="left",
            validate="one_to_one",
        )
    refined_clusters, split_stats = split_conflicting_clusters(
        clusters_for_split
    )
    tqdm.write(
        f"Split {split_stats['split_clusters']:,} conflicting clusters: "
        f"{split_stats['raw_clusters']:,} raw -> "
        f"{split_stats['refined_clusters']:,} refined "
        f"({split_stats['records_resplit']:,} records moved)"
    )

    stage("write clusters")
    merged = write_cluster_parquet(persons, refined_clusters, path=cluster_path)
    tqdm.write(f"Wrote {cluster_path}")

    stage("load graph")
    graph_path = (
        Path(args.graph_input).expanduser() if args.graph_input else None
    )
    graph = load_graph(graph_path, demo=args.demo)
    tqdm.write(
        f"Loaded graph: {graph.number_of_nodes():,} nodes / "
        f"{graph.number_of_edges():,} edges"
    )

    stage("relabel graph")
    node_to_cluster = dict(
        zip(merged["node_id"].astype(str), merged["cluster_id"].astype(str))
    )
    cluster_labels = {
        str(cluster_id): str(full_name)
        for cluster_id, full_name in (
            merged.sort_values("node_id")
            .drop_duplicates("cluster_id")
            .set_index("cluster_id")["full_name"]
            .items()
        )
    }
    cluster_confidences = {
        str(cluster_id): str(level)
        for cluster_id, level in (
            merged.drop_duplicates("cluster_id")
            .set_index("cluster_id")["confidence_level"]
            .items()
        )
    }
    cluster_graph, graph_build_stats = build_cluster_graph(
        graph,
        node_to_cluster,
        cluster_labels=cluster_labels,
        cluster_confidences=cluster_confidences,
        only_resolved=args.only_resolved,
    )
    tqdm.write(
        f"Relabeled graph: {cluster_graph.number_of_nodes():,} nodes / "
        f"{cluster_graph.number_of_edges():,} edges"
    )

    stage("prune graph")
    pruned, prune_stats = prune_graph_preserve_chains(
        cluster_graph, progress=progress
    )
    tqdm.write(
        f"Pruned graph: {pruned.number_of_nodes():,} nodes / "
        f"{pruned.number_of_edges():,} edges "
        f"({prune_stats['cycles']:,} cycles preserved)"
    )

    stage("write graphml")
    graphml_stats = write_graphml(pruned, graphml_path)
    tqdm.write(f"Wrote {graphml_path}")

    dashboard_written = False
    dashboard_clusters = 0
    if not args.no_dashboard:
        stage("dashboard")
        dashboard_started = time.time()

        # Cluster Studio's "by_cluster_size" sampling embeds only one cluster
        # per distinct size, which is far too narrow for a county-wide review.
        # Pass every matched cluster explicitly (optionally capped by
        # --sample-size) so all reviewed merges are available in the UI.
        cluster_sizes = merged.groupby("cluster_id").size()
        cluster_levels = (
            merged.drop_duplicates("cluster_id")
            .set_index("cluster_id")["confidence_level"]
            .to_dict()
        )
        matched_ids = cluster_sizes[cluster_sizes > 1].index.tolist()
        if args.sample_size and len(matched_ids) > args.sample_size:
            matched_ids = random.Random(args.seed).sample(
                matched_ids, args.sample_size
            )
        matched_ids.sort(
            key=lambda cluster_id: (
                -int(cluster_sizes[cluster_id]),
                str(cluster_levels.get(cluster_id, "")),
                str(cluster_id),
            )
        )
        numeric_clusters = pd.api.types.is_numeric_dtype(
            merged["cluster_id"]
        )
        dashboard_ids = [
            int(cluster_id) if numeric_clusters else str(cluster_id)
            for cluster_id in matched_ids
        ]
        dashboard_names = [
            f"Cluster {cluster_id} "
            f"(size {cluster_sizes[cluster_id]}, "
            f"{cluster_levels.get(cluster_id, 'UNKNOWN')})"
            for cluster_id in matched_ids
        ]

        dashboard_frame = refined_clusters[
            ["unique_id", "cluster_id", "confidence_level"]
        ]
        dashboard_sdf = linker._db_api.register(
            dashboard_frame, table_name="refined_clusters"
        )
        linker.visualisations.cluster_studio_dashboard(
            pairwise,
            dashboard_sdf,
            out_path=str(dashboard_path),
            cluster_ids=dashboard_ids,
            cluster_names=dashboard_names,
            overwrite=True,
        )
        dashboard_written = True
        dashboard_clusters = len(dashboard_ids)
        tqdm.write(
            f"Wrote {dashboard_path} with {dashboard_clusters:,} clusters "
            f"in {time.time() - dashboard_started:.1f}s"
        )
    else:
        bar.update(1)

    stage("audit")
    audit = cluster_audit(merged)
    print_audit(audit)

    stats: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "input": str(input_path),
        "output_dir": str(output_dir),
        "threshold": args.threshold,
        "training_enabled": training_enabled,
        "em_passes": args.em_passes if training_enabled else 0,
        "seed": args.seed,
        "load": load_stats,
        "split": split_stats,
        "audit": audit,
        "graph_input": str(graph_path) if graph_path else None,
        "graph_build": graph_build_stats,
        "pruning": prune_stats,
        "graphml": graphml_stats,
        "graphml_size_bytes": graphml_path.stat().st_size,
        "pairwise_matches": int(pairwise_count),
        "dashboard_written": dashboard_written,
        "dashboard_clusters": int(dashboard_clusters),
        "training_seconds": round(training_seconds, 2),
        "total_seconds": round(time.time() - started, 2),
    }
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    tqdm.write(f"Wrote {stats_path}")
    bar.close()

    print(f"\nDone in {stats['total_seconds']:.1f}s")
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument(
        "--graph-input",
        default=str(DEFAULT_GRAPH),
        help="pickled/GraphML/GEXF directed ownership graph (required unless --demo)",
    )
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=0,
        help="max clusters embedded in Cluster Studio (0 = all matched clusters)",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--em-passes", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--train",
        action="store_true",
        help="estimate p/u and run EM instead of the golden priors",
    )
    parser.add_argument(
        "--no-training",
        action="store_true",
        help="force deterministic golden priors (the default)",
    )
    parser.add_argument("--no-dashboard", action="store_true")
    parser.add_argument(
        "--only-resolved",
        action="store_true",
        help="drop graph edges with no resolved person endpoint",
    )
    parser.add_argument("--demo", action="store_true", help="use the sample graph")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_pipeline(args)
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
