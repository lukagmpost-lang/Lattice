"""Scrape Cuyahoga civil docket results for a list of names.

The scraper writes one JSONL record per target.  A record is only
``status="success"`` when the docket returned at least one row; empty pages
are written as ``no_results`` so they can be retried.  Network settings are
ordinary browser defaults: no TLS weakening and no proxy unless the operator
sets ``OSI_PROXY``.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from osi.loaders.io_utils import (
    append_record,
    atomic_write_json,
    iter_records,
    resume_targets,
)

_DEFAULT_ROOT = Path(__file__).resolve().parents[3]
BANDWIDTH_FILE = Path(
    os.environ.get(
        "OSI_BANDWIDTH_FILE", str(_DEFAULT_ROOT / "data" / "bandwidth_today.json")
    )
)
TARGETS_PATH = Path(
    os.environ.get(
        "OSI_SCRAPE_TARGETS", str(_DEFAULT_ROOT / "data" / "scrape_targets_29k.json")
    )
)
PROGRESS_PATH = Path(
    os.environ.get(
        "OSI_COURTS_PROGRESS", str(_DEFAULT_ROOT / "data" / "courts_progress.jsonl")
    )
)
BANDWIDTH_LIMIT_BYTES = 15 * 1024 * 1024 * 1024  # 15 GB
DEFAULT_DELAY_SECONDS = float(os.environ.get("OSI_SCRAPE_DELAY", "15"))
DEFAULT_EMPTY_ATTEMPTS = int(os.environ.get("OSI_EMPTY_RETRIES", "2"))


def load_bandwidth(path: str | Path = BANDWIDTH_FILE) -> dict:
    path = Path(path)
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"date": today, "bytes": 0}
    if not isinstance(data, dict) or data.get("date") != today:
        return {"date": today, "bytes": 0}
    try:
        data["bytes"] = max(0, int(data.get("bytes", 0)))
    except (TypeError, ValueError):
        data["bytes"] = 0
    return data


def save_bandwidth(bw: dict, path: str | Path = BANDWIDTH_FILE) -> None:
    try:
        atomic_write_json(bw, path)
    except OSError:
        pass


def check_bandwidth_limit(bw: dict) -> bool:
    """Return False when today's transfer budget is exhausted."""
    return int(bw.get("bytes", 0)) < BANDWIDTH_LIMIT_BYTES


def _has_evidence(record: dict) -> bool:
    return bool(record.get("rows"))


def load_targets(
    targets_path: str | Path = TARGETS_PATH,
    progress_path: str | Path = PROGRESS_PATH,
    *,
    max_empty_attempts: int = DEFAULT_EMPTY_ATTEMPTS,
) -> list[dict]:
    """Return targets that still need a verified result."""
    targets_path = Path(targets_path)
    if not targets_path.exists():
        return []
    try:
        targets = json.loads(targets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(targets, list):
        return []
    records = list(iter_records(progress_path))
    return resume_targets(
        targets,
        records,
        has_evidence=_has_evidence,
        empty_statuses={"no_results", "no_cases"},
        max_empty_attempts=max_empty_attempts,
    )


def _result_rows(page) -> list[dict]:
    rows = page.evaluate(
        """() => {
            const trs = document.querySelectorAll('table tr'); let out = [];
            for (let tr of trs) {
                const tds = tr.querySelectorAll('td');
                if (tds.length >= 5) out.push({
                    name: tds[0].innerText.trim(),
                    role: tds[2].innerText.trim(),
                    case_num: tds[3].innerText.trim(),
                    caption: tds[4].innerText.trim()
                });
            }
            return out;
        }"""
    )
    # Pagination controls and empty cells sometimes look like rows.
    return [row for row in rows if any(ch.isalpha() for ch in row.get("name", ""))]


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
    bandwidth_path: str | Path = BANDWIDTH_FILE,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    max_empty_attempts: int = DEFAULT_EMPTY_ATTEMPTS,
) -> None:
    targets = load_targets(
        targets_path,
        progress_path,
        max_empty_attempts=max_empty_attempts,
    )
    print(f"Remaining court targets: {len(targets)}", flush=True)
    if not targets:
        return

    proxy = os.environ.get("OSI_PROXY") or None
    with _browser(proxy) as browser:
        page = browser.new_page()
        bw = load_bandwidth(bandwidth_path)

        def track_response(response):
            try:
                length = response.headers.get("content-length")
                if length:
                    bw["bytes"] += int(length)
                else:
                    # The body is already in the browser cache; this counts the
                    # bytes that were transferred when Content-Length is absent.
                    bw["bytes"] += len(response.body() or b"")
            except Exception:
                pass

        page.on("response", track_response)

        def block_assets(route):
            if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
                route.abort()
            else:
                route.continue_()

        page.route("**/*", block_assets)

        for index, target in enumerate(targets):
            if not check_bandwidth_limit(bw):
                used_gb = bw["bytes"] / (1024**3)
                print(
                    f"\n[BANDWIDTH LIMIT] {used_gb:.2f} GB of 15 GB used. "
                    "Stopping scraper.",
                    flush=True,
                )
                save_bandwidth(bw, bandwidth_path)
                return
            try:
                page.goto(
                    "https://cpdocket.cp.cuyahogacounty.gov/",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                page.wait_for_timeout(1000)
                if page.locator("#SheetContentPlaceHolder_btnYes").count() > 0:
                    page.locator("#SheetContentPlaceHolder_btnYes").click()
                    page.wait_for_timeout(1500)

                page.locator("#SheetContentPlaceHolder_rbCivilName").click()
                page.wait_for_timeout(1500)
                page.fill(
                    "#SheetContentPlaceHolder_civilNameSearch_txtLastName",
                    target["last"],
                )
                page.fill(
                    "#SheetContentPlaceHolder_civilNameSearch_txtFirstName",
                    target["first"],
                )
                page.locator(
                    "#SheetContentPlaceHolder_civilNameSearch_btnSubmitName"
                ).click()
                page.wait_for_timeout(3000)

                rows = _result_rows(page)
                record = {
                    "node_key": target["node_key"],
                    "status": "success" if rows else "no_results",
                    "rows": rows,
                    "scraped_at": datetime.now().isoformat(timespec="seconds"),
                }
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
            finally:
                save_bandwidth(bw, bandwidth_path)
            time.sleep(delay_seconds)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", default=str(TARGETS_PATH))
    parser.add_argument("--progress", default=str(PROGRESS_PATH))
    parser.add_argument("--bandwidth", default=str(BANDWIDTH_FILE))
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument(
        "--empty-retries", type=int, default=DEFAULT_EMPTY_ATTEMPTS
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    main(
        targets_path=args.targets,
        progress_path=args.progress,
        bandwidth_path=args.bandwidth,
        delay_seconds=args.delay,
        max_empty_attempts=args.empty_retries,
    )
