"""Older direct-to-pickle marriage pipeline.

Kept for one-off runs against a single graph.  The merge module is the normal
entry point; both now use the same identity checks, so a case is only attached
when the searched person is one of its two parties.
"""

from __future__ import annotations

import argparse
import os
import pickle
import re
import time
from pathlib import Path

import networkx as nx

from osi.loaders.io_utils import atomic_pickle_dump
from osi.loaders.merge_jsonl_to_graph import PersonIndex, resolve_party_node
from osi.names import PersonIdentity, identities_match, name_from_node_key, person_identity

_DEFAULT_GRAPH = Path(os.path.expanduser("~/Desktop/cuyahoga_unified.pkl"))
_DEFAULT_OUT = Path(os.path.expanduser("~/Desktop/cuyahoga_unified_with_marriages.pkl"))
_CASE_RE = re.compile(r"\b((?:19|20)\d{2}ML\d+)\b", re.IGNORECASE)


def bypass_tc(page) -> None:
    page.goto(
        "https://probate.cuyahogacounty.gov/pa/",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    page.wait_for_timeout(1000)
    try:
        button = page.locator("input[type='submit']").first
        if button.is_visible(timeout=3000):
            button.click()
    except Exception:
        pass
    try:
        page.wait_for_selector("#mpContentPH_txtCaseNum", timeout=15000)
    except Exception:
        pass


def search_name(page, last: str, first: str) -> list[str]:
    """Phase 1: find ML case numbers for a person."""
    page.goto(
        "https://probate.cuyahogacounty.gov/pa/CaseSearch.aspx",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    page.wait_for_selector("#mpContentPH_txtLName", timeout=15000)
    page.fill("#mpContentPH_txtFName", first)
    page.fill("#mpContentPH_txtLName", last)
    page.select_option("#mpContentPH_ddlCaseCat", value="ML")
    page.locator("#mpContentPH_btnSearchByPerson").click()
    page.wait_for_timeout(2500)
    text = page.evaluate("() => document.body.innerText")
    return sorted(set(_CASE_RE.findall(text)))


def search_case(page, case_str: str) -> list[str]:
    """Phase 2: get the parties for a specific case."""
    year, cat, number = case_str[:4], case_str[4:6], case_str[6:]
    page.goto(
        "https://probate.cuyahogacounty.gov/pa/CaseSearch.aspx",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    page.wait_for_selector("#mpContentPH_txtCaseNum", timeout=15000)
    page.evaluate(
        """(args) => {
            document.querySelector('#mpContentPH_txtCaseYear').value = args.year;
            document.querySelector('#mpContentPH_txtCaseNum').value = args.num;
            const sel = document.querySelector('#mpContentPH_ddlCaseCat');
            for (let i=0; i<sel.options.length; i++) {
                if (sel.options[i].value === args.cat) { sel.selectedIndex = i; break; }
            }
        }""",
        {"year": year, "cat": cat, "num": number},
    )
    page.wait_for_timeout(500)
    page.locator("#mpContentPH_btnSearchByCase").click()
    page.wait_for_timeout(2500)
    rows = page.evaluate(
        """() => {
            const trs = document.querySelectorAll('table tr');
            let out = [];
            for (let tr of trs) {
                const tds = tr.querySelectorAll('td');
                if (tds.length >= 4) {
                    out.push({
                        name: tds[0].innerText.trim(),
                        role: tds[3].innerText.trim()
                    });
                }
            }
            return out;
        }"""
    )
    parties = [
        row["name"]
        for row in rows
        if row.get("role") in ("APPLICANT1", "APPLICANT2", "GROOM", "BRIDE")
        and row.get("name")
    ]
    return list(dict.fromkeys(parties))


def _target_identity(node_key: str, data: dict) -> PersonIdentity | None:
    value = data.get("name") or name_from_node_key(node_key)
    return person_identity(value) if value else None


def _voter_matched(data: dict) -> bool:
    # voter_file.py writes name_unique/dob/address.  The old check looked for
    # "unique", which no code path produced.
    return data.get("voter_match") in {"name_unique", "dob", "address"}


def _browser():
    from camoufox.sync_api import Camoufox

    return Camoufox(headless=True)


def run_pipeline(
    limit: int = 5,
    *,
    graph_path: str | Path = _DEFAULT_GRAPH,
    out_path: str | Path | None = _DEFAULT_OUT,
    case_delay_seconds: float = 2,
) -> int:
    graph_path = Path(graph_path)
    print(f"Loading graph: {graph_path}")
    with graph_path.open("rb") as handle:
        graph: nx.Graph = pickle.load(handle)

    targets: list[tuple[str, PersonIdentity]] = []
    for node, data in graph.nodes(data=True):
        if not str(node).startswith("owner|") or not _voter_matched(data):
            continue
        identity = _target_identity(str(node), data)
        if identity is None:
            continue
        targets.append((str(node), identity))
        if len(targets) >= limit:
            break

    added = 0
    with _browser() as browser:
        page = browser.new_page()
        bypass_tc(page)
        index = PersonIndex(graph)

        for position, (node_key, target) in enumerate(targets, 1):
            print(
                f"\n[{position}/{len(targets)}] Processing "
                f"{target.last}, {target.first} ({node_key})..."
            )
            try:
                case_numbers = search_name(page, target.last, target.first)
                if not case_numbers:
                    print("  No modern marriage cases found.")
                    continue
                print(f"  Found cases: {case_numbers}")
                for case_number in case_numbers:
                    time.sleep(case_delay_seconds)
                    parties = search_case(page, case_number)
                    if len(parties) != 2:
                        continue
                    matches = [
                        i
                        for i, party in enumerate(parties)
                        if identities_match(target, person_identity(party))
                    ]
                    if len(matches) != 1:
                        continue
                    spouse = parties[1 - matches[0]]
                    spouse_key = resolve_party_node(
                        graph, index, spouse, source="marriage_record"
                    )
                    if spouse_key is None or graph.has_edge(node_key, spouse_key):
                        continue
                    graph.add_edge(
                        node_key,
                        spouse_key,
                        relation="married_to",
                        source="marriage_record",
                        case_no=case_number,
                        reliability="B",
                        match_method="case_party_name",
                    )
                    added += 1
            except Exception as exc:
                print(f"  ERROR: {exc}")

    print(f"\nAdded {added} verified marriage edges.")
    if out_path is not None:
        atomic_pickle_dump(graph, out_path)
        print(f"Saved graph to {out_path}")
    return added


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default=str(_DEFAULT_GRAPH))
    parser.add_argument("--out", default=str(_DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--case-delay", type=float, default=2)
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    run_pipeline(
        limit=args.limit,
        graph_path=args.graph,
        out_path=args.out,
        case_delay_seconds=args.case_delay,
    )
