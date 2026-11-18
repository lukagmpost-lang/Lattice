"""Small I/O helpers shared by the Cuyahoga loaders.

All graph and cache writes go through a temporary file in the destination
directory so an interrupted run cannot leave a half-written pickle or JSON
document behind.
"""

from __future__ import annotations

import json
import os
import pickle
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator


def iter_records(path: str | Path) -> Iterator[dict]:
    """Yield JSON objects from a JSONL file, skipping malformed lines."""
    path = Path(path)
    if not path.exists():
        return
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def append_record(path: str | Path, record: dict) -> None:
    """Append one JSONL record and flush it to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def atomic_write_json(data: object, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_pickle_dump(graph: object, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        with tmp.open("wb") as handle:
            pickle.dump(graph, handle, protocol=pickle.HIGHEST_PROTOCOL)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def backup_file(path: str | Path) -> Path:
    """Copy a file aside with a timestamp; returns the backup path."""
    path = Path(path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.bak_{stamp}")
    shutil.copy2(path, backup)
    return backup


def resume_targets(
    targets: Iterable[dict],
    records: Iterable[dict],
    *,
    has_evidence,
    empty_statuses: set[str],
    max_empty_attempts: int = 2,
) -> list[dict]:
    """Filter scrape targets using verified progress.

    A target is finished only when a record carries evidence (court rows or a
    verified marriage party pair).  Empty results are retried up to
    ``max_empty_attempts``; old records written as ``success`` with an empty
    payload count as one of those attempts.
    """
    targets = list(targets)
    processed: set[str] = set()
    empty_counts: Counter[str] = Counter()
    for record in records:
        key = record.get("node_key")
        if not key:
            continue
        status = record.get("status")
        if status == "success":
            if has_evidence(record):
                processed.add(key)
            else:
                empty_counts[key] += 1
        elif status in empty_statuses:
            empty_counts[key] += 1
        # Errors are deliberately not counted so transient failures retry.
    return [
        target
        for target in targets
        if target.get("node_key") not in processed
        and empty_counts[target.get("node_key", "")] < max_empty_attempts
    ]


def empty_attempts(records: Iterable[dict], *, has_evidence, empty_statuses: set[str]) -> Counter[str]:
    """Count unverified/empty attempts per node key."""
    counts: Counter[str] = Counter()
    for record in records:
        key = record.get("node_key")
        if not key:
            continue
        status = record.get("status")
        if status == "success" and not has_evidence(record):
            counts[key] += 1
        elif status in empty_statuses:
            counts[key] += 1
    return counts
