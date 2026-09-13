from __future__ import annotations

from pathlib import Path

from self_coding.git_boundary import record_verified_change


def test_git_boundary_rejects_non_main_branch(monkeypatch, tmp_path: Path):
    def fake_git(_workspace: Path, *args: str) -> tuple[int, str]:
        if args == ("branch", "--show-current"):
            return 0, "feature/test"
        raise AssertionError(args)

    monkeypatch.setattr("self_coding.git_boundary._run_git", fake_git)

    result = record_verified_change(tmp_path, "test")

    assert result["ok"] is False
    assert result["stage"] == "branch"
    assert "must run from main" in str(result["error"])


def test_git_boundary_reports_clean_workspace_without_commit(monkeypatch, tmp_path: Path):
    calls: list[tuple[str, ...]] = []

    def fake_git(_workspace: Path, *args: str) -> tuple[int, str]:
        calls.append(args)
        if args == ("branch", "--show-current"):
            return 0, "main"
        if args == ("status", "--porcelain"):
            return 0, ""
        raise AssertionError(args)

    monkeypatch.setattr("self_coding.git_boundary._run_git", fake_git)

    result = record_verified_change(tmp_path, "test")

    assert result == {"ok": True, "stage": "record", "status": "no_changes"}
    assert calls == [("branch", "--show-current"), ("status", "--porcelain")]
