from __future__ import annotations

import re
import subprocess
from pathlib import Path


DEFAULT_AUTHOR_NAME = "Jarvis"
DEFAULT_AUTHOR_EMAIL = "jarvis@users.noreply.github.com"


def _run_git(workspace: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", "-C", str(workspace), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, result.stdout.strip() or result.stderr.strip()


def _safe_commit_title(goal: str) -> str:
    cleaned = re.sub(r"\s+", " ", goal).strip()[:72]
    return f"feat(self-coding): {cleaned or 'verified improvement'}"


def record_verified_change(workspace: Path, goal: str) -> dict[str, str | bool]:
    """Record verified self-coding changes without touching release/update state."""
    workspace = workspace.resolve()
    if not workspace.is_dir():
        return {"ok": False, "stage": "validate", "error": "Self-coding workspace does not exist."}

    code, branch = _run_git(workspace, "branch", "--show-current")
    if code != 0:
        return {"ok": False, "stage": "branch", "error": branch or "Unable to determine Git branch."}
    if branch != "main":
        return {"ok": False, "stage": "branch", "error": f"Verified self-coding must run from main, not {branch or 'detached HEAD'}."}

    code, status = _run_git(workspace, "status", "--porcelain")
    if code != 0:
        return {"ok": False, "stage": "status", "error": status or "Unable to read Git status."}
    if not status:
        return {"ok": True, "stage": "record", "status": "no_changes"}

    code, output = _run_git(workspace, "add", "-A")
    if code != 0:
        return {"ok": False, "stage": "add", "error": output or "Git add failed."}

    result = subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "-c",
            f"user.name={DEFAULT_AUTHOR_NAME}",
            "-c",
            f"user.email={DEFAULT_AUTHOR_EMAIL}",
            "commit",
            "-m",
            _safe_commit_title(goal),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return {"ok": False, "stage": "commit", "error": result.stdout.strip() or result.stderr.strip()}

    code, sha = _run_git(workspace, "rev-parse", "HEAD")
    if code != 0 or not sha:
        return {"ok": False, "stage": "commit", "error": "Commit succeeded but its SHA could not be read."}

    code, output = _run_git(workspace, "push", "origin", "HEAD:main")
    if code != 0:
        return {"ok": False, "stage": "push", "error": output or "Git push to origin/main failed.", "commit": sha}

    return {"ok": True, "stage": "record", "status": "pushed", "commit": sha}
