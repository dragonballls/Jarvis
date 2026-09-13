from __future__ import annotations

import subprocess
from pathlib import Path

from self_coding.git_boundary import record_verified_change


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


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


def test_git_boundary_commits_and_pushes_verified_change(tmp_path: Path):
    remote = tmp_path / "remote.git"
    workspace = tmp_path / "workspace"

    assert subprocess.run(["git", "init", "--bare", str(remote)], check=False).returncode == 0
    assert subprocess.run(["git", "init", "-b", "main", str(workspace)], check=False).returncode == 0
    assert git(workspace, "remote", "add", "origin", str(remote)).returncode == 0

    source = workspace / "app.py"
    source.write_text("print('hello')\n", encoding="utf-8")
    assert git(workspace, "add", "app.py").returncode == 0
    assert git(
        workspace,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-m",
        "initial",
    ).returncode == 0
    assert git(workspace, "push", "-u", "origin", "main").returncode == 0

    source.write_text("print('verified')\n", encoding="utf-8")
    result = record_verified_change(workspace, "Improve the verified coding path")

    assert result["ok"] is True
    assert result["status"] == "pushed"
    assert result["commit"]
    assert git(workspace, "status", "--porcelain").stdout.strip() == ""

    remote_head = git(remote, "rev-parse", "refs/heads/main")
    assert remote_head.returncode == 0
    assert remote_head.stdout.strip() == result["commit"]
