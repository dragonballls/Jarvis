from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path


DEFAULT_MODEL = "opencode/big-pickle"


def _find_opencode() -> str | None:
    """Locate the installed OpenCode CLI without opening a console window."""
    candidates = [
        shutil.which("opencode.cmd"),
        shutil.which("opencode"),
        os.path.join(os.environ.get("APPDATA", ""), "npm", "opencode.cmd"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def run_coding_agent(
    workspace: Path,
    goal: str,
    *,
    model: str = DEFAULT_MODEL,
    timeout: int = 1800,
) -> Generator[dict, None, None]:
    """Run the installed OpenCode coding agent headlessly in the Jarvis repo.

    OpenCode owns the coding-agent loop (planning, file edits, commands and
    verification). Jarvis only supervises the process and streams its output.
    No local LLM is started by this wrapper.
    """
    opencode = _find_opencode()
    if not opencode:
        yield {
            "type": "error",
            "error": "OpenCode CLI was not found on PATH or in %APPDATA%\\npm.",
            "final": True,
        }
        return

    prompt = (
        "You are Jarvis's autonomous coding agent. Work only inside the supplied "
        "repository. Inspect the existing code before editing. Make one or more "
        "useful, low-risk improvements requested by the goal. Preserve working "
        "functionality. Run relevant tests and verification after edits. Do not "
        "touch secrets, credentials, unrelated user files, or destructive system "
        "settings. Do not claim completion unless the implementation and tests "
        "actually succeed. When the work is verified, summarize the changes and "
        "verification results.\n\nGOAL:\n" + goal
    )

    args = [
        opencode,
        "run",
        "--format",
        "json",
        "--model",
        model,
        "--agent",
        "build",
        "--auto",
        "--dir",
        str(workspace),
        prompt,
    ]

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            args,
            cwd=str(workspace),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
    except OSError as exc:
        yield {"type": "error", "error": str(exc), "final": True}
        return

    assert process.stdout is not None
    try:
        for line in process.stdout:
            text = line.rstrip()
            if text:
                yield {"type": "tokens", "content": text + "\n"}
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        yield {
            "type": "error",
            "error": f"OpenCode coding run exceeded {timeout} seconds and was stopped.",
            "final": True,
        }
        return

    if return_code != 0:
        yield {
            "type": "error",
            "error": f"OpenCode coding agent exited with code {return_code}.",
            "final": True,
        }
        return

    yield {"type": "done", "content": "OpenCode coding run completed successfully.", "final": True}
