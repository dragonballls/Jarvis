from __future__ import annotations

from packaging.windows.app import should_run_gui


def test_gui_smoke_mode_runs_gui_without_general_smoke_mode(monkeypatch):
    monkeypatch.setenv("JARVIS_GUI_SMOKE_TEST", "1")
    monkeypatch.delenv("JARVIS_SMOKE_TEST", raising=False)
    assert should_run_gui() is True


def test_general_smoke_mode_does_not_request_gui(monkeypatch):
    monkeypatch.setenv("JARVIS_SMOKE_TEST", "1")
    monkeypatch.delenv("JARVIS_GUI_SMOKE_TEST", raising=False)
    assert should_run_gui() is False
