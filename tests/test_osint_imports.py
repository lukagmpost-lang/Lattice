import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from osi.loaders.osint import _to_networkx, load_osint_entity


ROOT = Path(__file__).resolve().parents[1]


def test_main_imports_without_pivot_planner(tmp_path):
    env = os.environ.copy()
    env["PIVOT_PLANNER_DIR"] = str(tmp_path / "missing-pivot-planner")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "src")))

    result = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_load_osint_entity_reports_missing_pivot_planner(tmp_path, monkeypatch):
    config = tmp_path / "entity.json"
    config.write_text(json.dumps({"query": "Ada Lovelace"}), encoding="utf-8")
    missing = tmp_path / "missing-pivot-planner"
    monkeypatch.setenv("PIVOT_PLANNER_DIR", str(missing))

    with pytest.raises(RuntimeError) as exc_info:
        load_osint_entity(config)

    message = str(exc_info.value)
    assert "pivot-planner" in message
    assert "PIVOT_PLANNER_DIR" in message
    assert str(missing) in message


def test_wikipedia_corroboration_preserves_base_confidence():
    graph = _to_networkx(
        {
            "nodes": [
                {"id": "Q1", "name": "Seed", "type": "person"},
                {"id": "Q2", "name": "Neighbor", "type": "person"},
            ],
            "edges": [
                {
                    "source": "Q1",
                    "target": "Q2",
                    "relation": "associated_with",
                    "confidence": 0.42,
                }
            ],
        },
        seed_qid="Q1",
        seed_attrs={"has_wikipedia": True, "sitelink_count": 3},
    )

    edge = graph["Seed"]["Neighbor"]
    assert edge["confidence"] == 0.42
    assert edge["wikipedia_corroborated"] is True
