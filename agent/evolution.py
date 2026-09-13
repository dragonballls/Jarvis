from __future__ import annotations

import subprocess
from collections.abc import Generator
from pathlib import Path

from core.opencode_agent import run_coding_agent
from self_coding.ecosystem import discover, format_report
from self_coding.git_boundary import record_verified_change


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
    if (workspace / "pyproject.toml").exists() or (workspace / "pytest.ini").exists() or (workspace / "requirements.txt").exists():
        commands.append(["python", "-m", "pytest", "-q", "tests"])
    if (workspace / "package.json").exists():
        commands.append(["npm", "test"])
    return commands


def _verify(workspace: Path) -> Generator[dict, None, bool]:
    code, output = _git(workspace, "diff", "--check")
    if code != 0:
        yield {"type": "autopilot", "event": "verification_failed", "check": "git diff --check", "output": output}
        return False

    commands = _verification_commands(workspace)
    if not commands:
        yield {
            "type": "autopilot",
            "event": "verification_failed",
            "check": "verification configuration",
            "output": "No supported project verification command was found.",
        }
        return False

    for command in commands:
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
    """Run an EMRG-style bounded self-improvement cycle with ecosystem discovery."""
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

    try:
        candidates = discover(goal)
        report = format_report(candidates)
    except Exception as exc:
        candidates = []
        report = f"External ecosystem discovery unavailable: {exc}"

    yield {
        "type": "autopilot",
        "event": "evolution",
        "stage": "discover",
        "status": "ecosystem_scan_complete",
        "candidates": len(candidates),
        "report": report,
    }

    prompt = (
        "Perform one controlled Jarvis self-improvement cycle. Follow this sequence: "
        "prepare, review the repository and its tests, use the external ecosystem "
        "discovery report to identify useful projects or forks, then discover the "
        "highest-value safe improvement, implement only that improvement, verify it, "
        "and summarize the result. Preserve existing functionality. You may inspect "
        "public repositories or forks and selectively adapt useful ideas, patterns, "
        "or code when their license permits and the change fits Jarvis. Never blindly "
        "copy an entire repository. Do not execute untrusted external repository code. "
        "Treat dependencies, scripts, credentials, and system changes as high risk. "
        "Do not create or publish forks automatically; use a fork only when it is "
        "necessary and explicitly supported by an authenticated GitHub workflow. "
        "Never modify secrets, credentials, unrelated files, or system settings. "
        "Do not install or invoke a local LLM. Only use remote AI. Do not commit or "
        "push changes yourself; return the workspace with verified modifications for "
        "Jarvis's isolated Git recording boundary.\n\nGOAL:\n" + goal + "\n\n" + report
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

    result = record_verified_change(workspace, goal)
    if not result.get("ok"):
        yield {
            "type": "autopilot",
            "event": "verification_failed",
            "check": f"self-coding Git record ({result.get('stage', 'unknown')})",
            "output": str(result.get("error", "Unable to record verified change.")),
        }
        yield {
            "type": "done",
            "content": "Evolution cycle verified the code but could not safely record the change in GitHub.",
            "final": True,
        }
        return

    yield {
        "type": "autopilot",
        "event": "evolution",
        "stage": "record",
        "status": str(result.get("status", "recorded")),
        "commit": result.get("commit", ""),
    }
    yield {"type": "done", "content": "Evolution cycle completed, verified, and recorded successfully.", "final": True}
