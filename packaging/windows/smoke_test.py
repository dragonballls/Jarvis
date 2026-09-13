from __future__ import annotations

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build" / "windows"
EXE = BUILD / "Jarvis.exe"
VERSION = BUILD / "VERSION"
LOG = BUILD / "jarvis.log"
SMOKE_TIMEOUT_SECONDS = 180
SUCCESS_MARKER = "Jarvis smoke test passed"


def read_log() -> str:
    if not LOG.is_file():
        return ""
    try:
        return LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def dump_log() -> None:
    if not LOG.is_file():
        print("No packaged Jarvis log was produced.")
        return
    try:
        print("----- packaged jarvis.log -----")
        print(read_log())
        print("----- end packaged jarvis.log -----")
    except OSError as exc:
        print(f"Could not read packaged Jarvis log: {exc}")


def run_smoke(executable: Path, label: str) -> None:
    # Prevent a prior successful run from satisfying the current smoke test.
    try:
        LOG.unlink(missing_ok=True)
    except OSError as exc:
        raise SystemExit(f"Could not reset packaged smoke log: {exc}")

    proc = subprocess.Popen([str(executable), "--smoke-test"], cwd=executable.parent)
    try:
        deadline = time.monotonic() + SMOKE_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            log_text = read_log()
            if SUCCESS_MARKER in log_text:
                print(f"{label} smoke test passed.")
                return
            if "smoke-test watchdog expired" in log_text:
                dump_log()
                raise SystemExit(f"{label} smoke test watchdog expired")
            returncode = proc.poll()
            if returncode is not None:
                if returncode != 0:
                    dump_log()
                    raise SystemExit(f"{label} smoke test exited with code {returncode}")
                # A clean process exit without the marker is not a passing verification.
                dump_log()
                raise SystemExit(f"{label} smoke test exited without a success marker")
            time.sleep(0.25)
        dump_log()
        raise SystemExit(
            f"{label} smoke test did not report success within {SMOKE_TIMEOUT_SECONDS} seconds"
        )
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> None:
    for required in (EXE, VERSION):
        if not required.is_file():
            raise SystemExit(f"Missing Windows Jarvis file: {required}")

    version = VERSION.read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit("Windows Jarvis VERSION file is empty")

    run_smoke(EXE, "Jarvis single-file")
    print(f"Jarvis Windows packaging smoke test passed for version {version}.")
    dump_log()


if __name__ == "__main__":
    main()
