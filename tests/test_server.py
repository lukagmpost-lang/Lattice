import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from osi.server import app

client = TestClient(app)


def _run_ids() -> list[str]:
    return [run["run_id"] for run in client.get("/api/runs").json()]


def test_get_runs_returns_a_list():
    response = client.get("/api/runs")
    assert response.status_code == 200
    runs = response.json()
    assert isinstance(runs, list)
    assert all(isinstance(run["run_id"], str) for run in runs)
    assert "simple-v1" in _run_ids()


def test_post_ask_returns_an_answer():
    response = client.post(
        "/api/ask",
        json={"run": "simple-v1", "question": "top 3 by pagerank", "use_llm": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    assert "answer" in body
    assert "alice" in body["answer"]
    assert "How sure:" in body["answer"]
    assert body["intent"] == "rank_nodes"
    assert body["method"] == "exact"
    assert body["trust"] == "stable"
    assert isinstance(body["runtime_ms"], int)


def test_post_ask_missing_run_is_404():
    response = client.post(
        "/api/ask",
        json={"run": "no-such-run-server", "question": "top 3 by pagerank", "use_llm": False},
    )
    assert response.status_code == 404


def test_upload_whatsapp_creates_a_saved_run():
    transcript = (
        b"Family Group\n"
        b"1/15/24, 10:00:00 AM - Alice: Hi\n"
        b"1/15/24, 10:01:00 AM - Bob: Hello\n"
    )

    response = client.post(
        "/api/uploads",
        data={"source": "auto"},
        files={"file": ("family.txt", transcript, "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "whatsapp"
    assert body["title"] == "Family Group"
    assert body["nodes"] == 2
    assert body["edges"] == 1
    assert body["run"] in _run_ids()
    summary = client.get(f"/api/runs/{body['run']}").json()
    assert summary["nodes"] == 2
    assert summary["components"] == 1


def test_upload_rejects_unrecognized_format():
    response = client.post(
        "/api/uploads",
        data={"source": "auto"},
        files={"file": ("notes.txt", b"just some notes", "text/plain")},
    )

    assert response.status_code == 400


def test_post_ask_unsupported_question_returns_the_helpful_message():
    response = client.post(
        "/api/ask",
        json={"run": "simple-v1", "question": "   ", "use_llm": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "unsupported"
    assert "I don't know how to answer that" in body["answer"]
    assert "top 10 by pagerank" in body["answer"]


def test_post_ask_open_question_describes_the_graph():
    response = client.post(
        "/api/ask",
        json={"run": "simple-v1", "question": "why is the graph shaped this way", "use_llm": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "discuss"
    assert "alice" in body["answer"]
    assert "assortativity" not in body["answer"]
    assert "clustering" not in body["answer"]


def test_post_ask_can_run_the_agent():
    response = client.post(
        "/api/ask",
        json={
            "run": "simple-v1",
            "question": "top 3 by pagerank",
            "use_llm": False,
            "use_agent": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "agent"
    assert body["method"] == "agent"
    assert body["answer"].strip()


def test_index_returns_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<select" in response.text
    assert "Upload chat" in response.text
    assert "Communities" in response.text
    assert "Tense relationships" in response.text
    assert "01 / Data" not in response.text
    assert "02 / Ask" not in response.text
    assert "Ask" in response.text
    assert "/api/converse" not in response.text


def test_api_rejects_remote_clients_when_no_token_is_configured(monkeypatch):
    monkeypatch.delenv("OSI_API_TOKEN", raising=False)
    remote = TestClient(app, client=("203.0.113.9", 50000))
    response = remote.get("/api/runs")
    assert response.status_code == 401
    assert "OSI_API_TOKEN" in response.json()["detail"]


def test_api_token_allows_a_remote_client(monkeypatch):
    monkeypatch.setenv("OSI_API_TOKEN", "correct-horse")
    remote = TestClient(app, client=("203.0.113.9", 50000))
    assert remote.get("/api/runs").status_code == 401
    assert (
        remote.get("/api/runs", headers={"x-api-token": "wrong"}).status_code == 401
    )
    response = remote.get("/api/runs", headers={"x-api-token": "correct-horse"})
    assert response.status_code == 200
    assert "simple-v1" in [run["run_id"] for run in response.json()]


def test_token_can_travel_in_a_query_for_browser_links(monkeypatch):
    monkeypatch.setenv("OSI_API_TOKEN", "correct-horse")
    remote = TestClient(app, client=("203.0.113.9", 50000))
    response = remote.get("/api/runs?token=correct-horse")
    assert response.status_code == 200
    assert remote.get("/api/runs?token=wrong").status_code == 401


def test_non_ascii_tokens_are_rejected_without_a_server_error(monkeypatch):
    monkeypatch.setenv("OSI_API_TOKEN", "correct-horse")
    remote = TestClient(app, client=("203.0.113.9", 50000))
    response = remote.get("/api/runs", params={"token": "caf\u00e9"})
    assert response.status_code == 401


def test_graph_view_is_not_public(monkeypatch):
    monkeypatch.delenv("OSI_API_TOKEN", raising=False)
    remote = TestClient(app, client=("203.0.113.9", 50000))
    assert remote.get("/graph/simple-v1").status_code == 401


def test_converse_endpoint_is_removed():
    response = client.post(
        "/api/converse", json={"run_id": "simple-v1", "question": "who is central?"}
    )
    assert response.status_code == 404


def test_import_rejects_an_empty_export_without_deleting_runs():
    response = client.post("/api/runs/import", json={"runs": []})
    assert response.status_code == 400
    assert "simple-v1" in _run_ids()


def test_import_rejects_unknown_columns_without_deleting_runs():
    response = client.post(
        "/api/runs/import",
        json={"runs": [{"id": "x", "evil; DROP TABLE runs": 1}]},
    )
    assert response.status_code == 400
    assert "simple-v1" in _run_ids()


def test_import_round_trip_keeps_the_store_usable():
    exported = client.get("/api/runs/export").json()
    response = client.post("/api/runs/import", json=exported)
    assert response.status_code == 200
    assert response.json()["imported"]["runs"] >= 1
    assert "simple-v1" in _run_ids()
    summary = client.get("/api/runs/simple-v1").json()
    assert summary["nodes"] > 0


def test_run_summary_handles_a_directed_graph():
    from osi import store
    import networkx as nx

    graph = nx.DiGraph()
    graph.add_edge("alice", "bob")
    graph.add_edge("carol", "bob")
    store.create_run("file", {"layer": "file"}, run_id="directed-v1")
    store.save_graph("directed-v1", "file", graph)
    summary = client.get("/api/runs/directed-v1").json()
    assert summary["nodes"] == 3
    assert summary["edges"] == 2
    assert summary["components"] == 1


def test_ask_defaults_to_no_llm(monkeypatch):
    calls = {}

    def fake_execute(run, question, use_llm=True, use_agent=False):
        calls["use_llm"] = use_llm
        calls["run"] = run
        return "answer", {
            "intent": "rank_nodes",
            "params": {},
            "method": "exact",
            "trust": "stable",
        }

    monkeypatch.setattr("osi.server._execute", fake_execute)
    response = client.post(
        "/api/ask", json={"run": "simple-v1", "question": "top 3 by pagerank"}
    )
    assert response.status_code == 200
    assert calls == {"use_llm": False, "run": "simple-v1"}
