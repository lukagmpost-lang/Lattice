"""Regression tests for the optional conversation helper."""

from __future__ import annotations

import networkx as nx

from osi import converse as converse_module


def test_cache_round_trip_uses_the_store_context_manager(tmp_path, monkeypatch):
    monkeypatch.setenv("OSI_STORE", str(tmp_path / "store.db"))
    conversation = [{"role": "user", "content": "earlier"}]
    converse_module._cache_store("run-1", "who is central?", conversation, "alice")
    assert (
        converse_module._cache_lookup("run-1", "who is central?", conversation)
        == "alice"
    )
    assert converse_module._cache_lookup("run-2", "who is central?", conversation) is None


def test_code_execution_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("OSI_ALLOW_CODE_EXEC", raising=False)
    result = converse_module._run("result = 1", nx.Graph(), [])
    assert result["ok"] is False
    assert "disabled" in result["error"]


def test_converse_does_not_mutate_the_callers_history(monkeypatch):
    history = [{"role": "user", "content": "earlier"}]
    calls = []

    monkeypatch.setattr(
        converse_module, "_resolve_question", lambda question, prior: question
    )

    def fake_llm(prompt, system=None, temperature=0.0):
        calls.append(prompt)
        return '{"action": "answer", "answer": "alice is central"}'

    monkeypatch.setattr(converse_module, "call_llm", fake_llm)
    monkeypatch.setenv("OSI_NO_CACHE", "1")

    result = converse_module.converse("who is central?", nx.Graph(), [], history=history)
    assert result["answer"] == "alice is central"
    assert history == [{"role": "user", "content": "earlier"}]
    assert calls
