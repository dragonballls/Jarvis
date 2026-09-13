from __future__ import annotations

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build" / "windows"
EXE = BUILD / "Jarvis.exe"
VERSION = BUILD / "VERSION"
LOG = BUILD / "jarvis.log"


def dump_log() -> None:
    if not LOG.is_file():
        print("No packaged Jarvis log was produced.")
        return
    try:
        print("----- packaged jarvis.log -----")
        print(LOG.read_text(encoding="utf-8", errors="replace"))
        print("----- end packaged jarvis.log -----")
    except OSError as exc:
        print(f"Could not read packaged Jarvis log: {exc}")


def run_smoke(executable: Path, label: str) -> None:
    proc = subprocess.Popen([str(executable), "--smoke-test"], cwd=executable.parent)
    try:
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            returncode = proc.poll()
            if returncode is not None:
                if returncode != 0:
                    dump_log()
                    raise SystemExit(f"{label} smoke test exited with code {returncode}")
                print(f"{label} smoke test passed.")
                return
            time.sleep(0.25)
        dump_log()
        raise SystemExit(f"{label} smoke test did not complete within 40 seconds")
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
