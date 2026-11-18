"""Pytest fixtures for OS-INT tests."""
import os
import tempfile
from pathlib import Path

import pytest


def has_run(run_id: str) -> bool:
    """Check if a run exists in the store."""
    from osi import store
    try:
        runs = store.list_runs()
        return any(run_id == run[0] for run in runs)
    except Exception:
        return False


@pytest.fixture
def temp_store(monkeypatch):
    """Point the store at a temporary file and seed the example graph.

    The environment variable is read on every store call, so no reload is
    needed. Tests that need a different store can override ``OSI_STORE``.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "store.db")
        monkeypatch.setenv("OSI_STORE", db_path)

        from osi import store
        from osi.loader import load_edge_list

        G = load_edge_list("examples/simple.csv")
        store.create_run(
            "file",
            {"source": "file", "path": "examples/simple.csv", "layer": "file"},
            "simple-v1",
            run_id="simple-v1",
        )
        store.save_graph("simple-v1", "file", G)

        yield "simple-v1"


@pytest.fixture(autouse=True)
def _isolated_store(temp_store):
    """Keep every test off the developer's real ``~/.osi/store.db``."""
    yield temp_store
