from __future__ import annotations

from pathlib import Path

import pytest

from agent import evolution
from core import opencode_agent


def test_evolution_has_emrg_cycle_stages() -> None:
    assert evolution.STAGES == ("prepare", "review", "discover", "improve", "verify", "record")


def test_evolution_refuses_dirty_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evolution, "_worktree_clean", lambda _workspace: False)
    events = list(evolution.run_evolution_cycle(tmp_path, "improve Jarvis"))
    assert events[-1]["final"] is True
    assert "clean Git worktree" in events[-1]["content"]


def test_engine_explicit_openhands_is_used(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[Path, str]] = []

    def fake_run_once(workspace: Path, goal: str):
        calls.append((workspace, goal))
        return [{"type": "done", "content": "ok", "final": True}]

    monkeypatch.setenv("JARVIS_AGENT_ENGINE", "openhands")
    monkeypatch.setattr("agent.openhands_runtime.openhands_available", lambda: True)
    monkeypatch.setattr("agent.openhands_runtime.run_once", fake_run_once)
    events = list(opencode_agent.run_coding_agent(tmp_path, "test goal"))
    assert calls == [(tmp_path.resolve(), "test goal")]
    assert events[-1]["content"] == "ok"


def test_engine_auto_uses_fallback_when_openhands_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_AGENT_ENGINE", "auto")
    monkeypatch.setattr("agent.openhands_runtime.openhands_available", lambda: False)
    monkeypatch.setattr(
        opencode_agent,
        "_run_opencode",
        lambda workspace, goal, model=opencode_agent.DEFAULT_MODEL, timeout=1800: iter(
            [{"type": "done", "content": "fallback", "final": True}]
        ),
    )
    events = list(opencode_agent.run_coding_agent(tmp_path, "test goal"))
    assert events[-1]["content"] == "fallback"


def test_openhands_adapter_never_selects_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JARVIS_OPENHANDS_MODEL", raising=False)
    monkeypatch.delenv("OPENHANDS_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    from agent.openhands_runtime import _model_name

    assert _model_name() == "gpt-5.5"
    assert "ollama" not in _model_name().lower()
