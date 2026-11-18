"""Scrape Cuyahoga probate marriage records for a list of names.

Only cases where the searched person is one of the two recorded parties are
written as ``success``.  Cases returned by a name search but naming two other
people are ``unverified``, so the merge step cannot turn them into edges and
the scraper can retry them later.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from osi.loaders.io_utils import (
    append_record,
    iter_records,
    resume_targets,
)
from osi.names import PersonIdentity, identities_match, person_identity

_DEFAULT_ROOT = Path(__file__).resolve().parents[3]
TARGETS_PATH = Path(
    os.environ.get(
        "OSI_SCRAPE_TARGETS", str(_DEFAULT_ROOT / "data" / "scrape_targets_29k.json")
    )
)
PROGRESS_PATH = Path(
    os.environ.get(
        "OSI_MARRIAGE_PROGRESS", str(_DEFAULT_ROOT / "data" / "marriage_progress.jsonl")
    )
)
DEFAULT_CASE_DELAY_SECONDS = float(os.environ.get("OSI_CASE_DELAY", "2"))
DEFAULT_EMPTY_ATTEMPTS = int(os.environ.get("OSI_EMPTY_RETRIES", "2"))
_CASE_RE = re.compile(r"\b((?:19|20)\d{2}ML\d+)\b", re.IGNORECASE)


def bypass_tc(page) -> None:
    page.goto(
        "https://probate.cuyahogacounty.gov/pa/",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    page.wait_for_timeout(2000)
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
    page.goto(
        "https://probate.cuyahogacounty.gov/pa/CaseSearch.aspx",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    page.wait_for_selector("#mpContentPH_txtLName", timeout=15000)
    page.evaluate(
        """(args) => {
            document.querySelector('#mpContentPH_txtFName').value = args.first;
            document.querySelector('#mpContentPH_txtLName').value = args.last;
            const sel = document.querySelector('#mpContentPH_ddlCaseCat');
            for (let i=0; i<sel.options.length; i++) {
                if (sel.options[i].value === 'ML') { sel.selectedIndex = i; break; }
            }
        }""",
        {"first": first, "last": last},
    )
    page.wait_for_timeout(500)
    page.locator("#mpContentPH_btnSearchByPerson").click()
    page.wait_for_timeout(1200)
    text = page.evaluate("() => document.body.innerText")
    return sorted(set(_CASE_RE.findall(text)))


def search_case(page, case_str: str) -> list[str]:
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
    page.wait_for_timeout(1200)
    rows = page.evaluate(
        """() => {
            const trs = document.querySelectorAll('table tr'); let out = [];
            for (let tr of trs) {
                const tds = tr.querySelectorAll('td');
                if (tds.length >= 4) out.push({
                    name: tds[0].innerText.trim(),
                    role: tds[3].innerText.trim()
                });
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


def verified_pair(
    parties: list[str],
    last: str,
    first: str,
) -> list[str] | None:
    """Return the two-party record only when the target is one of them."""
    if len(parties) != 2:
        return None
    target = PersonIdentity(last.strip().upper(), first.strip().upper())
    matches = [
        index
        for index, party in enumerate(parties)
        if identities_match(target, person_identity(party))
    ]
    return parties if len(matches) == 1 else None


def _has_evidence(record: dict) -> bool:
    return bool(record.get("parties"))


def load_targets(
    targets_path: str | Path = TARGETS_PATH,
    progress_path: str | Path = PROGRESS_PATH,
    *,
    max_empty_attempts: int = DEFAULT_EMPTY_ATTEMPTS,
) -> list[dict]:
    targets_path = Path(targets_path)
    if not targets_path.exists():
        return []
    try:
        targets = json.loads(targets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(targets, list):
        return []
    return resume_targets(
        targets,
        iter_records(progress_path),
        has_evidence=_has_evidence,
        empty_statuses={"no_cases", "no_results", "unverified"},
        max_empty_attempts=max_empty_attempts,
    )


def _browser(proxy: str | None):
    from camoufox.sync_api import Camoufox

    kwargs = {"headless": True}
    if proxy:
        kwargs["proxy"] = {"server": proxy}
    return Camoufox(**kwargs)


def main(
    *,
    targets_path: str | Path = TARGETS_PATH,
    progress_path: str | Path = PROGRESS_PATH,
    case_delay_seconds: float = DEFAULT_CASE_DELAY_SECONDS,
    max_empty_attempts: int = DEFAULT_EMPTY_ATTEMPTS,
) -> None:
    targets = load_targets(
        targets_path,
        progress_path,
        max_empty_attempts=max_empty_attempts,
    )
    print(f"Remaining marriage targets: {len(targets)}", flush=True)
    if not targets:
        return

    proxy = os.environ.get("OSI_PROXY") or None
    with _browser(proxy) as browser:
        page = browser.new_page()
        bypass_tc(page)

        for index, target in enumerate(targets):
            try:
                case_numbers = search_name(page, target["last"], target["first"])
                parties: list[dict] = []
                if case_numbers:
                    for case_number in case_numbers:
                        time.sleep(case_delay_seconds)
                        found = search_case(page, case_number)
                        pair = verified_pair(
                            found, target["last"], target["first"]
                        )
                        if pair is not None:
                            parties.append({"case": case_number, "parties": pair})

                if parties:
                    status = "success"
                elif case_numbers:
                    # The search returned cases, but none names the target as a
                    # party.  Retry rather than treating this as "no cases".
                    status = "unverified"
                else:
                    status = "no_cases"

                record = {
                    "node_key": target["node_key"],
                    "status": status,
                    "parties": parties,
                    "scraped_at": datetime.now().isoformat(timespec="seconds"),
                }
                if case_numbers:
                    record["cases_found"] = case_numbers
                append_record(progress_path, record)
                if index % 5 == 0:
                    print(f"Progress: {index}/{len(targets)}", flush=True)
            except Exception as exc:
                append_record(
                    progress_path,
                    {
                        "node_key": target["node_key"],
                        "status": "error",
                        "msg": str(exc),
                        "scraped_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", default=str(TARGETS_PATH))
    parser.add_argument("--progress", default=str(PROGRESS_PATH))
    parser.add_argument("--case-delay", type=float, default=DEFAULT_CASE_DELAY_SECONDS)
    parser.add_argument("--empty-retries", type=int, default=DEFAULT_EMPTY_ATTEMPTS)
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    main(
        targets_path=args.targets,
        progress_path=args.progress,
        case_delay_seconds=args.case_delay,
        max_empty_attempts=args.empty_retries,
    )
