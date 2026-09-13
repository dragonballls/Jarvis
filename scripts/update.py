#!/usr/bin/env python3
"""Safely update a Jarvis source checkout and packaged Windows executable."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
CANONICAL_REMOTE_URL = "https://github.com/dragonballls/Jarvis.git"
GITHUB_API = "https://api.github.com/repos/dragonballls/Jarvis/releases/tags/latest"
EXPECTED_EXE_ASSET = "Jarvis.exe"
EXPECTED_COMMIT_ASSET = "jarvis-commit.txt"


def run(command: list[str], *, cwd: Path = ROOT) -> int:
    print("$", " ".join(command))
    return subprocess.run(command, cwd=cwd, check=False).returncode


def working_tree_is_clean() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or "Unable to inspect git status.", file=sys.stderr)
        return False
    if result.stdout.strip():
        print("Refusing to update: working tree has local changes.", file=sys.stderr)
        print(result.stdout.strip(), file=sys.stderr)
        return False
    return True


def current_branch() -> str | None:
    result = subprocess.run(
        ["git", "branch", "--show-current"], cwd=ROOT, check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def current_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _ensure_jarvis_remote(remote: str) -> int:
    result = subprocess.run(
        ["git", "remote", "get-url", remote], cwd=ROOT, check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Unable to read git remote '{remote}'.", file=sys.stderr)
        return 1
    current_url = result.stdout.strip()
    normalized = current_url.rstrip("/").lower()
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if normalized.endswith("/dragonballls/jarvis"):
        return 0
    if "friday" in normalized:
        print(f"Migrating legacy Friday remote '{current_url}' to Jarvis.")
        return run(["git", "remote", "set-url", remote, CANONICAL_REMOTE_URL])
    print(f"Git remote '{remote}' is not the canonical Jarvis repository: {current_url}", file=sys.stderr)
    return 2


def _npm_command() -> str | None:
    if sys.platform == "win32":
        return shutil.which("npm.cmd") or shutil.which("npm")
    return shutil.which("npm")


def _clear_frontend_port() -> None:
    if sys.platform != "win32":
        return
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"], cwd=ROOT, check=False, capture_output=True, text=True
        )
    except OSError:
        return
    if result.returncode != 0:
        return
    pids: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local_address = parts[1]
        if parts[3].upper() == "LISTENING" and local_address.rsplit(":", 1)[-1] == "5173" and parts[4].isdigit():
            pids.add(parts[4])
    for pid in pids:
        subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], cwd=ROOT, check=False, capture_output=True, text=True)


def _frontend_dependencies_ready() -> bool:
    node_modules = DESKTOP / "node_modules"
    vite_package = node_modules / "vite" / "package.json"
    typescript_package = node_modules / "typescript" / "package.json"
    if sys.platform == "win32":
        vite_bin = node_modules / ".bin" / "vite.cmd"
        tsc_bin = node_modules / ".bin" / "tsc.cmd"
    else:
        vite_bin = node_modules / ".bin" / "vite"
        tsc_bin = node_modules / ".bin" / "tsc"
    return all(path.is_file() for path in (vite_package, typescript_package, vite_bin, tsc_bin))


def _install_frontend_dependencies(npm: str) -> int:
    _clear_frontend_port()
    result = run([npm, "ci"], cwd=DESKTOP)
    if result != 0:
        return result
    if _frontend_dependencies_ready():
        return 0
    print("npm ci completed but the frontend dependency tree is incomplete; retrying from a clean node_modules.", file=sys.stderr)
    _clear_frontend_port()
    node_modules = DESKTOP / "node_modules"
    if node_modules.exists():
        shutil.rmtree(node_modules, ignore_errors=False)
    return run([npm, "ci"], cwd=DESKTOP)


def rollback_to(commit: str) -> bool:
    if not working_tree_is_clean():
        print("Rollback refused because the working tree is no longer clean.", file=sys.stderr)
        return False
    if run(["git", "reset", "--hard", commit]) != 0:
        print(f"CRITICAL: unable to roll back Jarvis to known-good commit {commit}.", file=sys.stderr)
        return False
    print(f"Rolled Jarvis back to known-good commit {commit}.")
    return True


def _github_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "Jarvis-Updater/1.0", "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _release_asset(release: dict, name: str) -> dict | None:
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            return asset
    return None


def _download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "Jarvis-Updater/1.0", "Accept": "application/octet-stream"})
    with urlopen(request, timeout=180) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024)


def _release_for_commit(commit: str) -> tuple[Path, str] | None:
    try:
        release = _github_json(GITHUB_API)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        print(f"Unable to query the verified Windows release: {exc}", file=sys.stderr)
        return None

    commit_asset = _release_asset(release, EXPECTED_COMMIT_ASSET)
    exe_asset = _release_asset(release, EXPECTED_EXE_ASSET)
    if not commit_asset or not exe_asset:
        print("Verified Windows release is incomplete; waiting for CI to publish the executable.", file=sys.stderr)
        return None

    commit_temp = Path(tempfile.mkstemp(prefix="jarvis-commit-", suffix=".txt")[1])
    try:
        _download(commit_asset.get("browser_download_url", ""), commit_temp)
        published_commit = commit_temp.read_text(encoding="utf-8").strip()
    finally:
        commit_temp.unlink(missing_ok=True)
    if published_commit != commit:
        print(f"Windows release is for {published_commit[:12]}; requested {commit[:12]}.", file=sys.stderr)
        return None

    executable_temp = Path(tempfile.mkstemp(prefix="jarvis-update-", suffix=".exe")[1])
    try:
        _download(exe_asset.get("browser_download_url", ""), executable_temp)
        if executable_temp.stat().st_size < 1024 * 1024:
            raise RuntimeError("Downloaded Jarvis.exe is unexpectedly small")
        digest = exe_asset.get("digest")
        if isinstance(digest, str) and digest.startswith("sha256:"):
            expected = digest.split(":", 1)[1].lower()
            actual = hashlib.sha256(executable_temp.read_bytes()).hexdigest().lower()
            if actual != expected:
                raise RuntimeError("Downloaded Jarvis.exe failed GitHub SHA-256 verification")
        retained = executable_temp.with_name("Jarvis-verified.exe")
        os.replace(executable_temp, retained)
        return retained, published_commit
    except Exception:
        executable_temp.unlink(missing_ok=True)
        raise


def _restart_helper(python_exe: str, target_exe: Path, staged_exe: Path, args: list[str]) -> bool:
    helper = Path(tempfile.mkstemp(prefix="jarvis-exe-updater-", suffix=".py")[1])
    args_json = json.dumps(args)
    script = f'''from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

staged = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2]).resolve()
args = json.loads(sys.argv[3])
for _ in range(240):
    try:
        os.replace(staged, target)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        subprocess.Popen([str(target), *args], cwd=str(target.parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags, close_fds=True)
        break
    except (PermissionError, OSError):
        time.sleep(0.5)
else:
    sys.exit(1)
try:
    Path(__file__).unlink(missing_ok=True)
except OSError:
    pass
'''
    helper.write_text(script, encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        subprocess.Popen(
            [python_exe, str(helper), str(staged_exe), str(target_exe), args_json],
            cwd=str(target_exe.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
        return True
    except OSError as exc:
        print(f"Unable to launch executable replacement helper: {exc}", file=sys.stderr)
        helper.unlink(missing_ok=True)
        return False


def update_executable(remote_commit: str) -> int:
    target = Path(os.environ.get("JARVIS_AUTO_UPDATE_EXE", "")).resolve()
    if not target.is_file() or target.suffix.lower() != ".exe":
        print("Executable self-update is only available from the packaged Windows app.", file=sys.stderr)
        return 10
    try:
        verified = _release_for_commit(remote_commit)
    except Exception as exc:
        print(f"Windows executable download failed: {exc}", file=sys.stderr)
        return 11
    if verified is None:
        return 12
    staged_exe, published_commit = verified
    python_exe = sys.executable
    if getattr(sys, "frozen", False):
        python_exe = shutil.which("pythonw.exe") or shutil.which("python.exe") or shutil.which("pyw.exe") or shutil.which("py.exe") or ""
    if not python_exe:
        staged_exe.unlink(missing_ok=True)
        print("No external Python interpreter is available for the hidden replacement helper.", file=sys.stderr)
        return 13
    args = [arg for arg in os.environ.get("JARVIS_AUTO_UPDATE_ARGS", "").split("\0") if arg]
    if not _restart_helper(python_exe, target, staged_exe, args):
        staged_exe.unlink(missing_ok=True)
        return 14
    print(f"Verified Windows executable {published_commit[:12]} is staged for replacement.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely update Jarvis from GitHub")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--update-executable", action="store_true")
    args = parser.parse_args()

    if shutil.which("git") is None:
        print("git is required", file=sys.stderr)
        return 1

    migration_result = _ensure_jarvis_remote(args.remote)
    if migration_result == 1:
        return 3
    if migration_result == 2:
        return 4

    branch = current_branch()
    if branch != args.branch:
        if not working_tree_is_clean():
            print(f"Refusing to switch from '{branch or 'detached HEAD'}' to '{args.branch}' because local changes exist.", file=sys.stderr)
            return 2
        print(f"Local checkout is on '{branch or 'detached HEAD'}'; safely switching to '{args.branch}'.")
        if run(["git", "fetch", "--prune", args.remote, args.branch]) != 0:
            return 3
        if run(["git", "checkout", args.branch]) != 0:
            return 4

    if not working_tree_is_clean():
        return 2
    if run(["git", "fetch", "--prune", args.remote, args.branch]) != 0:
        return 3

    old_commit = current_commit()
    if old_commit is None:
        print("Unable to determine the current commit; refusing to update.", file=sys.stderr)
        return 4

    remote_ref = f"{args.remote}/{args.branch}"
    remote_result = subprocess.run(
        ["git", "rev-parse", remote_ref], cwd=ROOT, check=False, capture_output=True, text=True
    )
    remote_commit = remote_result.stdout.strip() if remote_result.returncode == 0 else ""
    if not remote_commit:
        print(f"Unable to resolve {remote_ref}; refusing to update.", file=sys.stderr)
        return 4
    if old_commit == remote_commit and not args.update_executable:
        print("Jarvis is up to date.")
        return 0

    if args.update_executable:
        if old_commit == remote_commit:
            print("Source is already current; checking whether a verified Windows executable is available.")
        else:
            try:
                verified = _release_for_commit(remote_commit)
            except Exception as exc:
                print(f"Windows executable verification failed: {exc}", file=sys.stderr)
                return 11
            if verified is None:
                return 12
            staged_exe, _ = verified
            if run(["git", "merge", "--ff-only", remote_ref]) != 0:
                staged_exe.unlink(missing_ok=True)
                return 4
            python_exe = shutil.which("pythonw.exe") or shutil.which("python.exe") or shutil.which("pyw.exe") or shutil.which("py.exe") or sys.executable
            args_to_restart = [arg for arg in os.environ.get("JARVIS_AUTO_UPDATE_ARGS", "").split("\0") if arg]
            target = Path(os.environ.get("JARVIS_AUTO_UPDATE_EXE", "")).resolve()
            if not target.is_file():
                staged_exe.unlink(missing_ok=True)
                rollback_to(old_commit)
                return 10
            if not _restart_helper(python_exe, target, staged_exe, args_to_restart):
                staged_exe.unlink(missing_ok=True)
                rollback_to(old_commit)
                return 14
            print(f"Jarvis source and Windows executable update staged for {remote_commit[:12]}.")
            return 0

        return 12

    if args.build:
        npm = _npm_command()
        if npm is None:
            return 7 if rollback_to(old_commit) else 9
        if not DESKTOP.is_dir():
            return 6 if rollback_to(old_commit) else 9
        if _install_frontend_dependencies(npm) != 0 or not _frontend_dependencies_ready():
            print("Frontend dependency installation failed or remained incomplete; rolling back the update.", file=sys.stderr)
            return 7 if rollback_to(old_commit) else 9
        if run([npm, "run", "build"], cwd=DESKTOP) != 0:
            print("Frontend build failed; rolling back the update.", file=sys.stderr)
            return 8 if rollback_to(old_commit) else 9

    if old_commit != remote_commit:
        if run(["git", "merge", "--ff-only", remote_ref]) != 0:
            return 4
    print("Jarvis is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
