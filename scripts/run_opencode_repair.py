"""Run Friday's OpenCode Big Pickle repair agent for up to one hour.

This is intentionally a thin process supervisor: OpenCode performs the coding,
while this script enforces the requested wall-clock budget and prevents a local
LLM/Ollama fallback.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


PROMPT = """
Run Friday's autonomous repair loop now.

Work directly in this repository. Fix real problems, starting with the current
GitHub Pages/local API 'Failed to fetch' problem, then continue through any
other verified failures you discover.

Use OpenCode Big Pickle only. Never use Ollama, any local LLM, or an alternate
provider/model. Inspect first, edit carefully, test every meaningful change,
repair failures, and keep going until the time budget expires.

Preserve Friday's security, approval, rollback, SafeExecutorAdapter, provider
routing, and GitHub integration protections. Do not touch credentials or .env
files. Do not claim a fix without verification.

Run the relevant Python and desktop tests as you work. Finish by checking the
git diff and reporting exactly what was changed and what verification passed.
""".strip()


def find_opencode() -> str:
    candidates = [shutil.which("opencode")]
    if os.name == "nt":
        candidates.extend(
            [
                shutil.which("opencode.cmd"),
                shutil.which("opencode.exe"),
            ]
        )

    for candidate in candidates:
        if candidate:
            return candidate

    raise SystemExit(
        "OpenCode was not found on PATH. Install/start OpenCode first, then rerun this script."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=60.0)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    opencode = find_opencode()
    deadline = time.monotonic() + max(1.0, args.minutes * 60.0)

    env = os.environ.copy()
    # Make the intended provider/model explicit and prevent accidental local
    # provider selection through environment-based configuration.
    env["OPENCODE_MODEL"] = "opencode/big-pickle"
    env.pop("OLLAMA_HOST", None)
    env.pop("OLLAMA_API_BASE", None)

    command = [
        opencode,
        "run",
        "--dir",
        str(root),
        "--model",
        "opencode/big-pickle",
        "--agent",
        "build",
        "--auto",
        PROMPT,
    ]

    print(f"Friday OpenCode repair: Big Pickle only, budget={args.minutes:g} minutes", flush=True)
    print(f"Repository: {root}", flush=True)

    process = subprocess.Popen(command, cwd=root, env=env)

    try:
        while process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                print("One-hour repair budget reached; stopping OpenCode cleanly.", flush=True)
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                return 124
            time.sleep(min(5.0, remaining))
    except KeyboardInterrupt:
        print("Repair run interrupted; stopping OpenCode.", flush=True)
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        return 130

    return int(process.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
