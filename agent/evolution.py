from __future__ import annotations

import subprocess
from collections.abc import Generator
from pathlib import Path

from core.opencode_agent import run_coding_agent


STAGES = ("prepare", "review", "discover", "improve", "verify", "record")


def _git(workspace: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", "-C", str(workspace), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, result.stdout.strip() or result.stderr.strip()


def _worktree_clean(workspace: Path) -> bool:
    code, output = _git(workspace, "status", "--porcelain")
    return code == 0 and not output


def _verification_commands(workspace: Path) -> list[list[str]]:
    commands: list[list[str]] = []
    if (workspace / "pyproject.toml").exists() or (workspace / "pytest.ini").exists():
        commands.append(["python", "-m", "pytest", "-q"])
    if (workspace / "package.json").exists():
        commands.append(["npm", "test", "--", "--runInBand"])
    return commands


def _verify(workspace: Path) -> Generator[dict, None, bool]:
    code, output = _git(workspace, "diff", "--check")
    if code != 0:
        yield {"type": "autopilot", "event": "verification_failed", "check": "git diff --check", "output": output}
        return False

    for command in _verification_commands(workspace):
        try:
            result = subprocess.run(
                command,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=900,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            yield {"type": "autopilot", "event": "verification_failed", "check": " ".join(command), "output": str(exc)}
            return False
        if result.returncode != 0:
            yield {
                "type": "autopilot",
                "event": "verification_failed",
                "check": " ".join(command),
                "output": (result.stdout + "\n" + result.stderr).strip()[-8000:],
            }
            return False
        yield {"type": "autopilot", "event": "verification_passed", "check": " ".join(command)}

    return True


def run_evolution_cycle(workspace: Path, goal: str) -> Generator[dict, None, None]:
    """Run an EMRG-style bounded self-improvement cycle.

    The cycle mirrors EMRG's prepare/review/discover/improve/verify/record loop,
    while keeping Jarvis's existing remote-only coding engine and requiring a
    clean starting worktree before autonomous mutation begins.
    """
    workspace = workspace.resolve()
    yield {"type": "autopilot", "event": "evolution", "stage": "prepare", "stages": list(STAGES)}

    if not workspace.is_dir():
        yield {"type": "error", "content": f"Evolution workspace does not exist: {workspace}", "final": True}
        return

    if not _worktree_clean(workspace):
        yield {
            "type": "error",
            "content": "Evolution requires a clean Git worktree so existing user changes are preserved.",
            "final": True,
        }
        return

    yield {"type": "autopilot", "event": "evolution", "stage": "review", "status": "clean_worktree"}
    yield {"type": "autopilot", "event": "evolution", "stage": "discover", "status": "delegating_to_agent"}

    prompt = (
        "Perform one controlled Jarvis self-improvement cycle. Follow this sequence: "
        "prepare, review the repository and its tests, discover the highest-value "
        "safe improvement, implement only that improvement, verify it, and summarize "
        "the result. Preserve existing functionality. Never modify secrets, credentials, "
        "unrelated files, or system settings. Do not install or invoke a local LLM. "
        "Only use remote AI. Do not commit unless verification succeeds.\n\nGOAL:\n" + goal
    )

    yield {"type": "autopilot", "event": "evolution", "stage": "improve"}
    for event in run_coding_agent(workspace, prompt):
        yield event

    yield {"type": "autopilot", "event": "evolution", "stage": "verify"}
    verification_events = []
    for event in _verify(workspace):
        verification_events.append(event)
        yield event
    failed = any(event.get("event") == "verification_failed" for event in verification_events)
    if failed:
        yield {"type": "done", "content": "Evolution cycle stopped because verification failed.", "final": True}
        return

    code, status = _git(workspace, "status", "--short")
    if code != 0:
        yield {"type": "done", "content": "Evolution finished, but Git status could not be read.", "final": True}
        return

    yield {
        "type": "autopilot",
        "event": "evolution",
        "stage": "record",
        "status": "verified",
        "changes": status,
    }
    yield {"type": "done", "content": "Evolution cycle completed and passed its verification gates.", "final": True}
