"""Merge Cuyahoga marriage and court scrape results into the unified graph.

Every edge added here is gated on the target appearing in the source record.
A name-only match is useful evidence, but it is not proof that the case belongs
to the person we searched for, so those edges are labelled ``reliability="B"``
instead of ``"A"``.

The module is importable for tests and callable as a script:

    python -m osi.loaders.merge_jsonl_to_graph --dry-run
    python -m osi.loaders.merge_jsonl_to_graph --apply
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import networkx as nx

from osi.loaders.io_utils import (
    atomic_pickle_dump,
    backup_file,
    iter_records,
)
from osi.names import (
    PersonIdentity,
    age_at_case,
    caption_sides,
    clean_name,
    docket_identity,
    identities_match,
    is_placeholder,
    name_from_node_key,
    party_key,
    person_identity,
    split_parties,
)

_DEFAULT_ROOT = Path(__file__).resolve().parents[3]
GRAPH_PATH = Path(
    os.path.expanduser(
        os.environ.get("OSI_CUYAHOGA_GRAPH", "~/Desktop/cuyahoga_unified.pkl")
    )
)
MARRIAGE_PATH = Path(
    os.environ.get(
        "OSI_MARRIAGE_PROGRESS",
        str(_DEFAULT_ROOT / "data" / "marriage_progress.jsonl"),
    )
)
COURTS_PATH = Path(
    os.environ.get(
        "OSI_COURTS_PROGRESS",
        str(_DEFAULT_ROOT / "data" / "courts_progress.jsonl"),
    )
)
TARGETS_PATH = Path(
    os.environ.get(
        "OSI_SCRAPE_TARGETS",
        str(_DEFAULT_ROOT / "data" / "scrape_targets_29k.json"),
    )
)

# Names that describe a role or an unknown party rather than a person are
# handled by osi.names.is_placeholder.

_PLAINTIFF_ROLES = {"PLAINTIFF", "PETITIONER", "APPELLANT", "COMPLAINANT"}
_DEFENDANT_ROLES = {"DEFENDANT", "DEBTOR", "RESPONDENT", "APPELLEE"}


def load_records(path: str | Path) -> Iterable[dict]:
    """Yield JSON objects from a JSONL progress file, skipping bad lines."""
    return iter_records(path)


def load_targets(path: str | Path | None = None) -> dict[str, dict]:
    """Load the scrape target list keyed by node key."""
    path = Path(path) if path is not None else TARGETS_PATH
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        row["node_key"]: row
        for row in rows
        if isinstance(row, dict) and row.get("node_key")
    }


def _target_identity(
    node_key: str,
    graph: nx.Graph,
    targets: dict[str, dict],
) -> PersonIdentity | None:
    """Resolve the searched person's identity without trusting a bad key."""
    data = graph.nodes.get(node_key, {})
    node_name = data.get("name") or name_from_node_key(node_key)
    parsed = person_identity(node_name) if node_name else None
    meta = targets.get(node_key)
    if meta:
        meta_identity = PersonIdentity(
            clean_name(meta.get("last")).upper(),
            clean_name(meta.get("first")).upper(),
        )
        if meta_identity.last and meta_identity.first:
            if parsed and identities_match(parsed, meta_identity):
                return PersonIdentity(
                    meta_identity.last,
                    meta_identity.first,
                    parsed.middle,
                    parsed.suffix,
                )
            return meta_identity
    return parsed


def _node_identity(name: str, data: dict) -> PersonIdentity | None:
    value = data.get("name") or name_from_node_key(name)
    return person_identity(value) if value else None


class PersonIndex:
    """Exact-name index over existing person nodes.

    Only exact last/first matches are considered.  The old prefix scan merged
    ``PAGAN`` with ``PAGANO`` and turned suffixes into surnames.
    """

    def __init__(self, graph: nx.Graph):
        self.graph = graph
        self.by_name: dict[tuple[str, str], list[str]] = defaultdict(list)
        for node, data in graph.nodes(data=True):
            if not str(node).startswith("owner|"):
                continue
            identity = _node_identity(str(node), data)
            if identity is not None:
                self.by_name[(identity.last, identity.first)].append(str(node))

    def candidates(self, identity: PersonIdentity) -> list[str]:
        return [
            node
            for node in self.by_name.get((identity.last, identity.first), [])
            if identities_match(identity, _node_identity(node, self.graph.nodes[node]))
        ]

    def add(self, node: str) -> None:
        identity = _node_identity(node, self.graph.nodes[node])
        if identity is not None:
            self.by_name[(identity.last, identity.first)].append(node)


def resolve_party_node(
    graph: nx.Graph,
    index: PersonIndex,
    name: object,
    *,
    source: str,
) -> str | None:
    """Find or create one party node without fuzzy name merging."""
    text = clean_name(name)
    if not text or is_placeholder(text):
        return None
    key = party_key(text)
    if key is None:
        # The string contains more than one party; callers must split first.
        return None
    if key in graph:
        return key

    identity = person_identity(text)
    if identity is not None:
        matches = index.candidates(identity)
        if len(matches) == 1:
            return matches[0]

    if key.startswith("org|"):
        graph.add_node(
            key,
            type="org",
            kind="organization",
            name=key[4:],
            source=source,
        )
    else:
        graph.add_node(
            key,
            type="owner",
            kind="person",
            name=key[6:],
            source=source,
        )
        index.add(key)
    return key


def _add_edge(
    graph: nx.Graph,
    a: str,
    b: str,
    *,
    relation: str,
    source: str,
    case_no: str,
    caption: str | None = None,
) -> bool:
    if a == b or graph.has_edge(a, b):
        return False
    if relation == "mentioned_in_case":
        attrs = {
            "relation": relation,
            "source": source,
            "case_no": case_no,
            "reliability": "C",
            "match_method": "docket_name_only",
        }
    else:
        attrs = {
            "relation": relation,
            "source": source,
            "case_no": case_no,
            "reliability": "B",
            "match_method": "case_party_name",
        }
    if caption:
        attrs["caption"] = caption
    graph.add_edge(a, b, **attrs)
    return True


def _target_side(
    sides: tuple[str, str],
    target: PersonIdentity,
    role: object,
) -> str | None:
    """Return the caption side containing the target, or None if unverified."""
    left, right = sides
    left_match = any(
        identities_match(target, person_identity(party))
        for party in split_parties(left)
    )
    right_match = any(
        identities_match(target, person_identity(party))
        for party in split_parties(right)
    )
    if left_match and not right_match:
        return "left"
    if right_match and not left_match:
        return "right"
    if left_match and right_match:
        # Same-name spouses are possible.  Use the docket role to decide which
        # side the searched person occupied; without that, skip the row.
        role_text = clean_name(role).upper()
        if role_text in _DEFENDANT_ROLES:
            return "right"
        if role_text in _PLAINTIFF_ROLES:
            return "left"
    return None


def merge_marriages(
    graph: nx.Graph,
    records: Iterable[dict],
    targets: dict[str, dict],
    index: PersonIndex | None = None,
) -> dict[str, int]:
    """Add only marriage edges whose case names the searched target."""
    index = index or PersonIndex(graph)
    stats = {"added": 0, "skipped": 0, "unverified": 0}
    for record in records:
        if record.get("status") != "success":
            continue
        target_key = record.get("node_key")
        if not target_key or target_key not in graph:
            stats["skipped"] += 1
            continue
        target = _target_identity(target_key, graph, targets)
        if target is None:
            stats["skipped"] += 1
            continue

        for party_data in record.get("parties") or []:
            names = party_data.get("parties") or []
            case_no = clean_name(party_data.get("case"))
            if len(names) != 2:
                stats["skipped"] += 1
                continue
            identities = [person_identity(name) for name in names]
            matches = [
                i for i, identity in enumerate(identities)
                if identities_match(target, identity)
            ]
            if len(matches) != 1:
                # Neither party is the searched person, or both are.  This is
                # the contamination that produced unrelated spouse edges.
                stats["unverified"] += 1
                continue
            spouse_index = 1 - matches[0]
            spouse_name = names[spouse_index]
            if is_placeholder(spouse_name):
                stats["skipped"] += 1
                continue
            if identities_match(target, identities[spouse_index]):
                stats["skipped"] += 1
                continue
            spouse_key = resolve_party_node(
                graph, index, spouse_name, source="marriage_record"
            )
            if spouse_key is None:
                stats["skipped"] += 1
                continue
            if _add_edge(
                graph,
                target_key,
                spouse_key,
                relation="married_to",
                source="marriage_record",
                case_no=case_no,
            ):
                stats["added"] += 1
    return stats


def merge_courts(
    graph: nx.Graph,
    records: Iterable[dict],
    targets: dict[str, dict],
    index: PersonIndex | None = None,
) -> dict[str, int]:
    """Add court edges only when the target is named in the case caption."""
    index = index or PersonIndex(graph)
    stats = {
        "added": 0,
        "skipped": 0,
        "unverified": 0,
        "no_rows": 0,
        "underage": 0,
    }
    for record in records:
        if record.get("status") != "success":
            continue
        target_key = record.get("node_key")
        if not target_key or target_key not in graph:
            stats["skipped"] += 1
            continue
        rows = record.get("rows") or []
        if not rows:
            stats["no_rows"] += 1
            continue
        target = _target_identity(target_key, graph, targets)
        if target is None:
            stats["skipped"] += 1
            continue
        dob = graph.nodes[target_key].get("date_of_birth")

        for row in rows:
            caption = clean_name(row.get("caption"))
            case_no = clean_name(row.get("case_num"))
            sides = caption_sides(caption)
            if sides is None:
                stats["unverified"] += 1
                continue
            side = _target_side(sides, target, row.get("role"))
            if side is None:
                stats["unverified"] += 1
                continue
            adult = age_at_case(dob, case_no)
            if adult is False:
                stats["underage"] += 1
                continue
            other_side = sides[1] if side == "left" else sides[0]
            relation = (
                "divorced_from"
                if case_no.upper().startswith("DR-")
                else "litigated_with"
            )
            for party in split_parties(other_side):
                if is_placeholder(party):
                    continue
                other_identity = person_identity(party)
                if identities_match(target, other_identity):
                    continue
                other_key = resolve_party_node(
                    graph, index, party, source="court_record"
                )
                if other_key is None:
                    continue
                if _add_edge(
                    graph,
                    target_key,
                    other_key,
                    relation=relation,
                    source="court_record",
                    case_no=case_no,
                    caption=caption,
                ):
                    stats["added"] += 1
    return stats


def merge_courts_mentioned(
    graph: nx.Graph,
    records: Iterable[dict],
    targets: dict[str, dict],
    index: PersonIndex | None = None,
) -> dict[str, int]:
    """Add 'mentioned_in_case' edges when the target appears in a docket row
    but NOT in the case caption (i.e., not a caption party).
    """
    index = index or PersonIndex(graph)
    stats = {"added": 0, "skipped": 0, "unverified": 0, "underage": 0}
    for record in records:
        if record.get("status") != "success":
            continue
        target_key = record.get("node_key")
        if not target_key or target_key not in graph:
            stats["skipped"] += 1
            continue
        target = _target_identity(target_key, graph, targets)
        if target is None:
            stats["skipped"] += 1
            continue
        dob = graph.nodes[target_key].get("date_of_birth")

        for row in record.get("rows") or []:
            caption = clean_name(row.get("caption"))
            sides = caption_sides(caption)
            if sides is None:
                stats["unverified"] += 1
                continue
            # Only process rows where target is NOT a caption party
            in_caption = any(
                identities_match(target, person_identity(p))
                for side in sides for p in split_parties(side)
            )
            if in_caption:
                continue

            # Docket row name must match target
            row_ident = docket_identity(row.get("name"))
            if not identities_match(target, row_ident):
                continue

            case_no = clean_name(row.get("case_num"))
            adult = age_at_case(dob, case_no)
            if adult is False:
                stats["underage"] += 1
                continue

            # Target is on the side indicated by the docket role
            role = str(row.get("role") or "").strip().upper()
            if role in _DEFENDANT_ROLES:
                side = "right"
            elif role in _PLAINTIFF_ROLES:
                side = "left"
            else:
                stats["unverified"] += 1
                continue

            other_side = sides[1] if side == "left" else sides[0]
            for party in split_parties(other_side):
                if is_placeholder(party):
                    continue
                other_identity = person_identity(party)
                if identities_match(target, other_identity):
                    continue
                other_key = resolve_party_node(
                    graph, index, party, source="court_record"
                )
                if other_key is None:
                    continue
                if _add_edge(
                    graph,
                    target_key,
                    other_key,
                    relation="mentioned_in_case",
                    source="court_record",
                    case_no=case_no,
                    caption=caption,
                ):
                    stats["added"] += 1
    return stats


def rebuild_source_edges(
    graph: nx.Graph,
    *,
    sources: tuple[str, ...] = ("marriage_record", "court_record"),
) -> int:
    """Remove every edge previously created by the gated loaders."""
    doomed = [
        (u, v)
        for u, v, data in graph.edges(data=True)
        if data.get("source") in sources
    ]
    graph.remove_edges_from(doomed)
    return len(doomed)


def run(
    *,
    graph_path: str | Path = GRAPH_PATH,
    marriage_path: str | Path = MARRIAGE_PATH,
    courts_path: str | Path = COURTS_PATH,
    targets_path: str | Path | None = TARGETS_PATH,
    apply: bool = False,
    rebuild: bool = False,
    include_mentioned: bool = False,
) -> dict[str, object]:
    """Merge both progress files, returning counts and the graph."""
    graph_path = Path(graph_path)
    with graph_path.open("rb") as handle:
        graph = pickle.load(handle)
    before_nodes = graph.number_of_nodes()
    before_edges = graph.number_of_edges()
    targets = load_targets(targets_path) if targets_path else {}

    removed = 0
    if rebuild:
        removed = rebuild_source_edges(graph)

    index = PersonIndex(graph)
    marriages = merge_marriages(
        graph, load_records(marriage_path), targets, index=index
    )
    courts = merge_courts(
        graph, load_records(courts_path), targets, index=index
    )
    courts_mentioned = {}
    if include_mentioned:
        courts_mentioned = merge_courts_mentioned(
            graph, load_records(courts_path), targets, index=index
        )

    summary = {
        "before_nodes": before_nodes,
        "before_edges": before_edges,
        "after_nodes": graph.number_of_nodes(),
        "after_edges": graph.number_of_edges(),
        "removed_edges": removed,
        "marriages": marriages,
        "courts": courts,
    }
    if include_mentioned:
        summary["courts_mentioned"] = courts_mentioned
    if apply:
        backup = backup_file(graph_path)
        atomic_pickle_dump(graph, graph_path)
        summary["backup"] = str(backup)
        summary["written"] = str(graph_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default=str(GRAPH_PATH))
    parser.add_argument("--marriage", default=str(MARRIAGE_PATH))
    parser.add_argument("--courts", default=str(COURTS_PATH))
    parser.add_argument("--targets", default=str(TARGETS_PATH))
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the merged graph (a timestamped backup is made first)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report counts without writing (the default)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="remove existing marriage_record/court_record edges before merging",
    )
    parser.add_argument(
        "--include-mentioned",
        action="store_true",
        help="add 'mentioned_in_case' edges (docket name match, not caption party)",
    )
    args = parser.parse_args()

    summary = run(
        graph_path=args.graph,
        marriage_path=args.marriage,
        courts_path=args.courts,
        targets_path=args.targets or None,
        apply=args.apply,
        rebuild=args.rebuild,
        include_mentioned=args.include_mentioned,
    )
    print(json.dumps(summary, indent=2))
    if not args.apply:
        print("dry run: pass --apply to write the graph")


if __name__ == "__main__":
    main()
