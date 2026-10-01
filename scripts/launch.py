#!/usr/bin/env python3
"""Start Jarvis safely and keep live updates in place without browser reloads."""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "scripts" / "update.py"
LOG_DIR = ROOT / "logs"
LAUNCH_LOG = LOG_DIR / "launcher.log"
AUTO_UPDATE_INTERVAL = 30
STARTUP_TASK_NAME = "Jarvis UI"
LEGACY_STARTUP_TASK_NAME = "Friday UI"
STARTUP_RETRY_DELAY = 5
MAX_STARTUP_RETRY_DELAY = 30
JARVIS_URL = "http://127.0.0.1:5173/"


def _log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    with LAUNCH_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")
    print(message, file=sys.stderr)


def print_colored(text: str, color_code: str = "37") -> None:
    print(f"\033[{color_code}m{text}\033[0m")


def _ensure_windows_startup_task() -> None:
    if sys.platform != "win32":
        return
    subprocess.run(["schtasks", "/Delete", "/TN", LEGACY_STARTUP_TASK_NAME, "/F"], capture_output=True, text=True, timeout=30, check=False)
    task_command = subprocess.list2cmdline([sys.executable, str(Path(__file__).resolve()), "--ui", "--startup"])
    result = subprocess.run(
        ["schtasks", "/Create", "/SC", "ONLOGON", "/TN", STARTUP_TASK_NAME, "/TR", task_command, "/F"],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 0:
        _log(f"Could not register automatic Windows startup for Jarvis (code {result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
    else:
        _log("Jarvis Windows startup task is installed for the current user.")


def _detach_windows_ui() -> bool:
    if sys.platform != "win32" or os.environ.get("JARVIS_DETACHED_UI") == "1" or "--startup" in sys.argv[1:]:
        return False
    detached_process = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    new_process_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    env = os.environ.copy()
    env["JARVIS_DETACHED_UI"] = "1"
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--ui", "--startup"],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, creationflags=detached_process | new_process_group, env=env,
    )
    return True


def _auto_update_monitor(root: str, update_event: threading.Event, stop_event: threading.Event):
    raw_interval = os.environ.get("JARVIS_AUTO_UPDATE_INTERVAL", str(AUTO_UPDATE_INTERVAL))
    try:
        interval = max(1, int(raw_interval))
    except ValueError:
        interval = AUTO_UPDATE_INTERVAL
    first_check = True
    while not stop_event.is_set():
        if not first_check and stop_event.wait(interval):
            return
        first_check = False
        try:
            branch = subprocess.run(["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True, timeout=15, check=False).stdout.strip()
            if branch != "main":
                _log(f"Auto-update paused: local checkout is on '{branch or 'detached HEAD'}', not main.")
                continue
            status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, capture_output=True, text=True, timeout=15, check=False)
            if status.returncode != 0 or status.stdout.strip():
                if status.stdout.strip():
                    _log("Auto-update paused: local changes are present; refusing to overwrite them.")
                continue
            fetch = subprocess.run(["git", "fetch", "origin", "main", "--prune"], cwd=root, capture_output=True, text=True, timeout=60, check=False)
            if fetch.returncode != 0:
                continue
            local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=15, check=False).stdout.strip()
            remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=root, capture_output=True, text=True, timeout=15, check=False).stdout.strip()
            if local and remote and local != remote:
                _log(f"Auto-update detected new main: {local[:12]} -> {remote[:12]}.")
                update_event.set()
                return
        except (OSError, subprocess.SubprocessError, ValueError):
            continue


def _start_auto_update_monitor(root: str, update_event: threading.Event, stop_event: threading.Event):
    monitor = threading.Thread(target=_auto_update_monitor, args=(root, update_event, stop_event), name="jarvis-auto-updater", daemon=True)
    monitor.start()
    return monitor


def _terminate_processes(procs: list[subprocess.Popen]):
    for proc in procs:
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and any(p.poll() is None for p in procs):
        time.sleep(0.2)
    for proc in procs:
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass


def _frontend_port_is_ready() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 5173), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_for_port(host: str, port: int, proc: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last_error = exc
        if proc.poll() is not None:
            raise RuntimeError(f"Jarvis UI service exited before port {port} became ready (exit code {proc.returncode}).")
        time.sleep(0.25)
    raise RuntimeError(f"Jarvis UI service did not become ready on {host}:{port} within {timeout:.0f}s ({last_error}).")


def _start_api_process(desktop: str) -> subprocess.Popen:
    proc = subprocess.Popen([sys.executable, os.path.join(desktop, "api_server.py")], cwd=desktop)
    try:
        _wait_for_port("127.0.0.1", 8080, proc)
    except Exception:
        _terminate_processes([proc])
        raise
    return proc


def _restart_api_process(procs: list[subprocess.Popen], desktop: str) -> None:
    old_api = procs[0] if procs else None
    if old_api is not None:
        _terminate_processes([old_api])
    procs[0:1] = [_start_api_process(desktop)]


def _start_ui_processes(desktop: str) -> list[subprocess.Popen]:
    if sys.platform == "win32":
        node_cmd = shutil.which("node.exe") or shutil.which("node")
        vite_js = os.path.join(desktop, "node_modules", "vite", "bin", "vite.js")
        if not node_cmd:
            raise RuntimeError("Node.js was not found on PATH; cannot start the Jarvis frontend.")
        if not os.path.isfile(vite_js):
            raise RuntimeError(f"Vite entrypoint was not found: {vite_js}")
        front_cmd = [node_cmd, vite_js, "--host", "127.0.0.1"]
    else:
        front_cmd = ["npm", "run", "dev", "--", "--host", "127.0.0.1"]
    procs: list[subprocess.Popen] = []
    try:
        procs.append(_start_api_process(desktop))
        if _frontend_port_is_ready():
            print_colored("Jarvis UI already running — reusing existing Vite server.", "32")
            return procs
        front = subprocess.Popen(front_cmd, cwd=desktop)
        procs.append(front)
        _wait_for_port("127.0.0.1", 5173, front)
        return procs
    except Exception:
        _terminate_processes(procs)
        raise


def _find_edge_app() -> str | None:
    """Locate Microsoft Edge so Jarvis gets its own app window on Windows."""
    candidates = [
        shutil.which("msedge.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _open_ui_browser():
    """Open Jarvis as a dedicated app window without browser chrome."""
    if sys.platform == "win32":
        edge = _find_edge_app()
        if edge:
            args = [
                edge,
                f"--app={JARVIS_URL}",
                "--new-window",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ]
            env = os.environ.copy()
            env["JARVIS_APP_WINDOW"] = "1"
            subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, env=env)
            print_colored(f"Jarvis app window ready — opening {JARVIS_URL}", "32")
            return
    print_colored(f"Jarvis UI ready — opening {JARVIS_URL}", "32")
    webbrowser.open(JARVIS_URL)


def _recover_dead_processes(procs: list[subprocess.Popen], desktop: str) -> None:
    if len(procs) >= 1 and procs[0].poll() is not None:
        procs[0:1] = [_start_api_process(desktop)]
    if len(procs) >= 2 and procs[1].poll() is not None:
        if sys.platform == "win32":
            node_cmd = shutil.which("node.exe") or shutil.which("node")
            vite_js = os.path.join(desktop, "node_modules", "vite", "bin", "vite.js")
            if not node_cmd or not os.path.isfile(vite_js):
                raise RuntimeError("Vite entrypoint is unavailable during frontend recovery.")
            front_cmd = [node_cmd, vite_js, "--host", "127.0.0.1"]
        else:
            front_cmd = ["npm", "run", "dev", "--", "--host", "127.0.0.1"]
        if _frontend_port_is_ready():
            print_colored("Jarvis UI already running — keeping existing Vite server.", "32")
            return
        front = subprocess.Popen(front_cmd, cwd=desktop)
        _wait_for_port("127.0.0.1", 5173, front)
        procs[1:2] = [front]


def _restart_launcher_without_reopening_browser() -> None:
    """Start the updated launcher and hand off ownership of the live UI."""
    env = os.environ.copy()
    env["JARVIS_HANDOFF"] = "1"
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--ui", "--startup"],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        env=env,
    )


def _launch_ui():
    root = str(ROOT)
    desktop = os.path.join(root, "desktop")
    print_colored("Jarvis desktop UI starting…", "36")
    retry_delay = STARTUP_RETRY_DELAY
    browser_opened = os.environ.get("JARVIS_HANDOFF") == "1"

    while True:
        update_event = threading.Event()
        stop_event = threading.Event()
        _start_auto_update_monitor(root, update_event, stop_event)
        procs: list[subprocess.Popen] = []
        handed_off = False
        try:
            procs = _start_ui_processes(desktop)
            retry_delay = STARTUP_RETRY_DELAY
            if not browser_opened:
                _open_ui_browser()
                browser_opened = True

            while True:
                time.sleep(1.0)
                if update_event.is_set():
                    print_colored("\nJarvis update detected — applying in place; browser will stay open…", "33")
                    stop_event.set()
                    result = _run_update(build=False)
                    if result == 0:
                        try:
                            _restart_api_process(procs, desktop)
                            _restart_launcher_without_reopening_browser()
                            handed_off = True
                            print_colored("Jarvis updated. The new launcher is taking over automatically.", "32")
                            return
                        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                            _log(f"Jarvis handoff failed; keeping current launcher alive: {exc}")
                    else:
                        _log("Live update was not applied; keeping the current Jarvis session running.")
                    update_event.clear()
                    stop_event.clear()
                    _start_auto_update_monitor(root, update_event, stop_event)
                elif any(p.poll() is not None for p in procs):
                    print_colored("\nJarvis service stopped — recovering only the failed service…", "33")
                    _recover_dead_processes(procs, desktop)
        except KeyboardInterrupt:
            print_colored("\nShutting down Jarvis UI…", "33")
            stop_event.set()
            _terminate_processes(procs)
            return
        except RuntimeError as exc:
            _log(f"Jarvis UI startup/recovery failed: {exc}")
            stop_event.set()
            _terminate_processes(procs)
            if handed_off:
                return
            print_colored(f"Jarvis UI will retry automatically in {retry_delay}s instead of exiting.", "33")
            time.sleep(retry_delay)
            retry_delay = min(MAX_STARTUP_RETRY_DELAY, retry_delay * 2)
        finally:
            stop_event.set()
            if not handed_off:
                _terminate_processes(procs)


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
    args = sys.argv[1:]
    if "--ui" in args and sys.platform == "win32" and "--startup" not in args:
        _ensure_windows_startup_task()
    if "--ui" in args and _detach_windows_ui():
        print_colored("Jarvis UI detached — it will keep running after this PowerShell window closes.", "32")
        return 0
    if "--ui" in args:
        _run_update(build=True)
        _launch_ui()
        return 0
    return subprocess.run([sys.executable, str(ROOT / "main.py"), *args], cwd=ROOT, check=False).returncode


def _run_update(*, build: bool = False) -> int:
    command = [sys.executable, str(UPDATER)]
    if build:
        command.append("--build")
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode not in (0, 2, 3, 4):
        _log(f"Jarvis update failed (code {result.returncode}); keeping current checkout.")
    elif result.returncode in (2, 4):
        _log("Jarvis update was skipped because the local checkout is not safely fast-forwardable; using current checkout.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
