from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
API_HOST = "127.0.0.1"
API_PORT = 8080
UI_HOST = "127.0.0.1"
UI_PORT = 5173
SMOKE_WATCHDOG_SECONDS = 60
STARTUP_DELAY_SECONDS = 3
AUTO_UPDATE_INTERVAL_SECONDS = 30

LOG = Path.home() / "jarvis.log"


class QuietHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        log(f"HTTP server error from {client_address}: {sys.exc_info()[1]}")


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} {message}\n"
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass


def hard_exit(code: int) -> None:
    os._exit(code)


def active_workspace() -> Path | None:
    raw = os.environ.get("JARVIS_WORKSPACE", "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser().resolve()
    return candidate if candidate.exists() else None


def dist_root() -> Path:
    workspace = active_workspace()
    if workspace is not None:
        candidate = workspace / "desktop" / "dist"
        if (candidate / "index.html").is_file():
            return candidate
    bundled = ROOT / "desktop" / "dist"
    return bundled


def start_static_server(port: int = UI_PORT) -> QuietHTTPServer:
    dist = dist_root().resolve()
    if not (dist / "index.html").is_file():
        raise RuntimeError(f"Jarvis frontend bundle is missing: {dist}")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            relative = parsed.path.lstrip("/") or "index.html"
            if relative == "" or relative.endswith("/"):
                relative = f"{relative}index.html" if relative else "index.html"
            target = (dist / relative).resolve()
            if dist not in target.parents and target != dist:
                self.send_error(403)
                return
            if not target.is_file():
                self.send_error(404)
                return
            body = target.read_bytes()
            content_type = "text/html; charset=utf-8"
            suffix = target.suffix.lower()
            if suffix == ".js":
                content_type = "text/javascript; charset=utf-8"
            elif suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif suffix == ".json":
                content_type = "application/json; charset=utf-8"
            elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}:
                content_type = "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = QuietHTTPServer((UI_HOST, port), Handler)
    threading.Thread(target=server.serve_forever, name="jarvis-ui-server", daemon=True).start()
    return server


def wait_for_port(host: str, port: int, timeout: float = 30) -> None:
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            try:
                sock.connect((host, port))
                return
            except OSError:
                time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for {host}:{port}")


def http_text(url: str) -> tuple[int, str] | None:
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        log(f"HTTP request failed for {url}: {exc}")
        return None


def start_api_server_thread() -> None:
    import hypercorn.asyncio
    from hypercorn.config import Config
    from desktop.api_server import app

    config = Config()
    config.bind = [f"{API_HOST}:{API_PORT}"]
    config.accesslog = None
    config.errorlog = None

    def runner() -> None:
        asyncio.run(hypercorn.asyncio.serve(app, config))

    threading.Thread(target=runner, name="jarvis-api", daemon=True).start()


def run_api_process() -> None:
    import hypercorn.asyncio
    from hypercorn.config import Config
    from desktop.api_server import app

    config = Config()
    config.bind = [f"{API_HOST}:{API_PORT}"]
    asyncio.run(hypercorn.asyncio.serve(app, config))


def _run_no_window(args, **kwargs):
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(args, startupinfo=startupinfo, creationflags=creationflags, **kwargs)


def prepare_self_coding_workspace() -> Path:
    configured = os.environ.get("JARVIS_SELF_CODING_WORKSPACE", "").strip()
    if configured:
        workspace = Path(configured).expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace
    workspace = Path.home() / "Jarvis-SelfCoding-Workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def ensure_workspace_repo(workspace: Path) -> None:
    git_dir = workspace / ".git"
    if git_dir.exists():
        return
    source = Path(__file__).resolve().parents[2]
    if (source / ".git").exists():
        _run_no_window(["git", "clone", "--", str(source), str(workspace)], check=False)


def ensure_workspace_build(workspace: Path) -> None:
    return


def quart_health_check_sync():
    import asyncio
    import sys

    workspace = active_workspace()
    if workspace is not None:
        sys.path.insert(0, str(workspace))
    sys.path.insert(1, str(ROOT))
    from desktop.api_server import app

    async def check():
        client = app.test_client()
        response = await client.get("/api/v1/health")
        body = await response.get_data(as_text=True)
        return response.status_code, body

    return asyncio.run(check())


def arm_smoke_watchdog(seconds: float = SMOKE_WATCHDOG_SECONDS) -> None:
    def expire() -> None:
        log(f"smoke-test watchdog expired after {seconds:.0f} seconds")
        hard_exit(2)

    timer = threading.Timer(seconds, expire)
    timer.daemon = True
    timer.start()


def smoke_test() -> None:
    dist = dist_root()
    if not dist.exists():
        raise RuntimeError(f"Jarvis frontend bundle is missing: {dist}")
    os.environ["JARVIS_SMOKE_TEST"] = "1"
    ui_server = start_static_server(port=0)
    smoke_port = int(ui_server.server_address[1])
    log(f"smoke-test UI listening on {UI_HOST}:{smoke_port}")
    try:
        wait_for_port(UI_HOST, smoke_port)
        ui = http_text(f"http://{UI_HOST}:{smoke_port}/")
        if ui is None or ui[0] != 200:
            raise RuntimeError("Jarvis UI did not return HTTP 200 on the root page")
        html = ui[1]
        if "<title>Jarvis</title>" not in html:
            raise RuntimeError("Jarvis UI root page did not contain the expected title")
        if "/Friday/assets/" in html:
            raise RuntimeError("Windows UI bundle incorrectly references /Friday/ assets")
        if "/assets/" not in html:
            raise RuntimeError("Jarvis UI root page did not contain a production asset reference")
        log("smoke-test UI checks passed")
        status, body = quart_health_check_sync()
        if status != 200:
            raise RuntimeError(f"Jarvis API health endpoint returned HTTP {status}: {body}")
        log("smoke-test API health passed")
        # This marker is the CI contract consumed by packaging/windows/smoke_test.py.
        log("Jarvis smoke test passed")
    finally:
        ui_server.shutdown()
        ui_server.server_close()


def install_startup() -> None:
    if os.name != "nt" or "--smoke-test" in sys.argv or "--api-server" in sys.argv:
        return
    try:
        import winreg

        exe = Path(sys.executable).resolve()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Jarvis", 0, winreg.REG_SZ, f'"{exe}" --startup')
    except OSError as exc:
        log(f"Could not install startup registration: {exc}")


def _auto_update_loop(workspace: Path) -> None:
    while True:
        time.sleep(AUTO_UPDATE_INTERVAL_SECONDS)
        try:
            result = _run_no_window(
                ["git", "fetch", "origin", "main", "--prune"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                log("Auto-update fetch failed; keeping current version.")
                continue
            head = _run_no_window(
                ["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True, text=True, check=False
            )
            remote = _run_no_window(
                ["git", "rev-parse", "origin/main"], cwd=workspace, capture_output=True, text=True, check=False
            )
            if head.returncode != 0 or remote.returncode != 0:
                continue
            local_sha = head.stdout.strip()
            remote_sha = remote.stdout.strip()
            if not local_sha or local_sha == remote_sha:
                continue
            updater = workspace / "scripts" / "update.py"
            if not updater.is_file():
                log("Auto-update skipped: updater script is missing from the workspace.")
                continue
            updater_python = sys.executable
            if getattr(sys, "frozen", False):
                updater_python = shutil.which("python.exe") or shutil.which("python") or shutil.which("py.exe") or shutil.which("py")
                if not updater_python:
                    log("Auto-update skipped: no external Python interpreter is available.")
                    continue
            env = os.environ.copy()
            env["JARVIS_AUTO_UPDATE_EXE"] = str(Path(sys.executable).resolve())
            env["JARVIS_AUTO_UPDATE_PARENT_PID"] = str(os.getpid())
            env["JARVIS_AUTO_UPDATE_ARGS"] = json.dumps(sys.argv[1:])
            result = _run_no_window(
                [updater_python, str(updater), "--update-executable"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
                env=env,
            )
            if result.returncode == 0:
                log("Verified Windows executable update is staged; shutting down for replacement.")
                hard_exit(0)
            detail = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
            log(f"Auto-update not installed; keeping current version: {detail[0] if detail else 'unknown error'}")
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            log(f"Auto-update loop error; keeping current version: {exc}")


def main() -> None:
    if "--smoke-test" in sys.argv:
        arm_smoke_watchdog()
        log("smoke-test starting")
        smoke_test()
        log("smoke-test completed")
        hard_exit(0)
    if "--api-server" in sys.argv:
        run_api_process()
        return
    if not (ROOT / "desktop" / "dist" / "index.html").exists():
        raise SystemExit(f"Jarvis frontend bundle is missing: {ROOT / 'desktop' / 'dist' / 'index.html'}")
    workspace = prepare_self_coding_workspace()
    os.environ["JARVIS_WORKSPACE"] = str(workspace)
    ensure_workspace_repo(workspace)
    ensure_workspace_build(workspace)
    import webview

    install_startup()
    start_static_server()
    threading.Thread(target=_auto_update_loop, args=(workspace,), name="jarvis-auto-update", daemon=True).start()
    start_api_server_thread()
    try:
        wait_for_port(API_HOST, API_PORT, timeout=60)
        wait_for_port(UI_HOST, UI_PORT, timeout=60)
        time.sleep(STARTUP_DELAY_SECONDS)
        webview.create_window(
            "Jarvis",
            f"http://{UI_HOST}:{UI_PORT}/",
            width=1440,
            height=900,
            min_size=(1050, 700),
        )
        webview.start()
    except Exception as exc:
        log(f"Jarvis UI failed to start: {exc}")
        raise


if __name__ == "__main__":
    main()
