from __future__ import annotations

import asyncio
import multiprocessing
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

API_HOST = "127.0.0.1"
API_PORT = 8080
UI_HOST = "127.0.0.1"
UI_PORT = 5173
SMOKE_WATCHDOG_SECONDS = 35.0
REPO_URL = "https://github.com/dragonballls/Jarvis.git"
REPO_ZIP_URL = "https://github.com/dragonballls/Jarvis/archive/refs/heads/main.zip"
WORKSPACE_NAME = "Jarvis-SelfCoding-Workspace"
AUTO_UPDATE_INTERVAL = 30


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


ROOT = resource_root()


def active_workspace() -> Path | None:
    configured = os.environ.get("JARVIS_WORKSPACE", "").strip()
    if configured:
        workspace = Path(configured).expanduser()
        if workspace.is_dir():
            return workspace
    return None


def dist_root() -> Path:
    workspace = active_workspace()
    if workspace is not None and (workspace / "desktop" / "dist" / "index.html").is_file():
        return workspace / "desktop" / "dist"
    return ROOT / "desktop" / "dist"


def log_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "jarvis.log"
    return Path.cwd() / "jarvis.log"


def log(message: str) -> None:
    line = message.rstrip() + "\n"
    try:
        with log_path().open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass
    try:
        if sys.stdout is not None:
            print(message, flush=True)
    except OSError:
        pass


def hard_exit(code: int) -> None:
    os._exit(code)


def self_coding_workspace() -> Path:
    return Path.home() / WORKSPACE_NAME


def _git_clone_workspace(workspace: Path) -> bool:
    git = shutil.which("git.exe") or shutil.which("git")
    if not git:
        return False
    try:
        subprocess.run(
            [git, "clone", "--depth", "1", "--branch", "main", REPO_URL, str(workspace)],
            cwd=workspace.parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        log("Self-coding workspace cloned as a real Git repository")
        return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        log(f"Git clone unavailable; using safe archive bootstrap: {exc}")
        shutil.rmtree(workspace, ignore_errors=True)
        return False


def _initialize_archive_workspace(workspace: Path) -> None:
    git = shutil.which("git.exe") or shutil.which("git")
    if not git:
        raise RuntimeError("Git is required for Jarvis self-coding verification.")
    result = subprocess.run([git, "init"], cwd=workspace, check=False, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git init failed")
    for args in (
        [git, "config", "user.name", "Jarvis"],
        [git, "config", "user.email", "jarvis@localhost"],
        [git, "add", "-A"],
        [git, "commit", "-m", "Jarvis bootstrap baseline"],
    ):
        result = subprocess.run(args, cwd=workspace, check=False, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Git bootstrap command failed")
    log("Self-coding workspace initialized with a local Git baseline")


def _archive_workspace(workspace: Path) -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="jarvis-bootstrap-"))
    archive_path = temp_dir / "jarvis-main.zip"
    extracted = temp_dir / "extracted"
    try:
        request = Request(REPO_ZIP_URL, headers={"User-Agent": "Jarvis/1.0"})
        with urlopen(request, timeout=60) as response:
            archive_path.write_bytes(response.read())
        with zipfile.ZipFile(archive_path) as archive:
            bad = [name for name in archive.namelist() if Path(name).is_absolute() or Path(name).drive or ".." in Path(name).parts]
            if bad:
                raise RuntimeError("GitHub source archive contained an unsafe path")
            archive.extractall(extracted)
        roots = [p for p in extracted.iterdir() if p.is_dir()]
        if len(roots) != 1:
            raise RuntimeError("Unexpected GitHub source archive layout")
        source = roots[0]
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)
        shutil.copytree(source, workspace)
        _initialize_archive_workspace(workspace)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def prepare_self_coding_workspace() -> Path:
    workspace = self_coding_workspace()
    if (workspace / ".git").is_dir() and (workspace / "agent").is_dir():
        return workspace
    workspace.parent.mkdir(parents=True, exist_ok=True)
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
    try:
        log(f"Preparing self-coding workspace: {workspace}")
        if not _git_clone_workspace(workspace):
            _archive_workspace(workspace)
        if not (workspace / ".git").is_dir():
            raise RuntimeError("Jarvis self-coding workspace is not a Git repository")
        if not (workspace / "agent").is_dir():
            raise RuntimeError("Jarvis self-coding workspace is missing the agent package")
        log("Self-coding workspace ready")
        return workspace
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        log("Self-coding workspace preparation failed:\n" + traceback.format_exc())
        raise


def wait_for_port(host: str, port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"Jarvis service did not become ready on {host}:{port}")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return


def start_static_server(port: int = UI_PORT) -> ThreadingHTTPServer:
    dist = dist_root()
    if not dist.is_dir() or not (dist / "index.html").is_file():
        raise RuntimeError(f"Frontend bundle missing: {dist / 'index.html'}")
    def handler(*args, **kwargs):
        return QuietHandler(*args, directory=str(dist), **kwargs)
    server = ThreadingHTTPServer((UI_HOST, port), handler)
    thread = threading.Thread(target=server.serve_forever, name="jarvis-static", daemon=True)
    thread.start()
    return server


async def _api_server() -> None:
    workspace = active_workspace()
    if workspace is not None:
        sys.path.insert(0, str(workspace))
    sys.path.insert(1, str(ROOT))
    log(f"API server importing desktop.api_server from {workspace or ROOT}")
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    from desktop.api_server import app
    config = Config()
    config.bind = [f"{API_HOST}:{API_PORT}"]
    config.accesslog = None
    config.errorlog = None
    config.loglevel = "warning"
    await serve(app, config, shutdown_trigger=lambda: asyncio.Future())


def run_api_server_thread() -> threading.Thread:
    def runner() -> None:
        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            asyncio.run(_api_server())
        except Exception:
            log("API server crashed:\n" + traceback.format_exc())
    thread = threading.Thread(target=runner, name="jarvis-api", daemon=True)
    thread.start()
    return thread


def run_api_process() -> None:
    """Legacy compatibility entry point; packaged Jarvis uses the in-process thread."""
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(_api_server())
    except Exception:
        log("API server crashed:\n" + traceback.format_exc())
        raise


def http_text(url: str) -> tuple[int, str] | None:
    try:
        with urlopen(url, timeout=3) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except (OSError, URLError):
        return None


async def quart_health_check() -> tuple[int, str]:
    workspace = active_workspace()
    if workspace is not None:
        sys.path.insert(0, str(workspace))
    sys.path.insert(1, str(ROOT))
    from desktop.api_server import app
    client = app.test_client()
    response = await client.get("/api/v1/health")
    body = await response.get_data(as_text=True)
    return response.status_code, body


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
        status, body = asyncio.run(quart_health_check())
        if status != 200:
            raise RuntimeError(f"Jarvis API health endpoint returned HTTP {status}: {body}")
        log("smoke-test API health passed")
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
    except OSError:
        pass


def _workspace_is_clean(workspace: Path, git: str) -> bool:
    result = subprocess.run([git, "status", "--porcelain", "--untracked-files=all"], cwd=workspace, capture_output=True, text=True, timeout=15, check=False)
    return result.returncode == 0 and not result.stdout.strip()


def _restart_after_update() -> None:
    env = os.environ.copy()
    env["JARVIS_UPDATED_RESTART"] = "1"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        subprocess.Popen([str(Path(sys.executable).resolve()), *sys.argv[1:]], cwd=str(active_workspace() or ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags, close_fds=True, env=env)
        hard_exit(0)
    except OSError as exc:
        log(f"Automatic restart after update failed: {exc}")


def _auto_update_loop(workspace: Path) -> None:
    if os.environ.get("JARVIS_SMOKE_TEST") == "1" or os.environ.get("JARVIS_UPDATED_RESTART") == "1":
        return
    git = shutil.which("git.exe") or shutil.which("git")
    if not git:
        log("Auto-update disabled: Git was not found on PATH.")
        return
    while True:
        time.sleep(AUTO_UPDATE_INTERVAL)
        try:
            if not _workspace_is_clean(workspace, git):
                log("Auto-update paused: self-coding workspace has local changes.")
                continue
            fetch = subprocess.run([git, "fetch", "origin", "main", "--prune"], cwd=workspace, capture_output=True, text=True, timeout=60, check=False)
            if fetch.returncode != 0:
                log("Auto-update fetch failed; retaining the current Jarvis version.")
                continue
            local = subprocess.run([git, "rev-parse", "HEAD"], cwd=workspace, capture_output=True, text=True, timeout=15, check=False).stdout.strip()
            remote = subprocess.run([git, "rev-parse", "origin/main"], cwd=workspace, capture_output=True, text=True, timeout=15, check=False).stdout.strip()
            if not local or not remote or local == remote:
                continue
            log(f"Auto-update detected main change: {local[:12]} -> {remote[:12]}.")
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
            result = subprocess.run([updater_python, str(updater), "--build"], cwd=workspace, capture_output=True, text=True, timeout=900, check=False, env=os.environ.copy())
            if result.returncode == 0:
                log("Jarvis source and frontend update completed; restarting onto the updated workspace.")
                _restart_after_update()
            else:
                detail = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
                log(f"Auto-update build failed; keeping current version: {detail[0] if detail else 'unknown error'}")
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
    import webview
    install_startup()
    start_static_server()
    threading.Thread(target=_auto_update_loop, args=(workspace,), name="jarvis-auto-update", daemon=True).start()
    run_api_server_thread()
    try:
        wait_for_port(API_HOST, API_PORT, timeout=30.0)
        wait_for_port(UI_HOST, UI_PORT, timeout=10.0)
        log("Jarvis services ready; opening desktop window")
        webview.create_window("Jarvis", f"http://{UI_HOST}:{UI_PORT}/", width=1440, height=900, min_size=(1050, 700), resizable=True, text_select=True)
        webview.start(gui="edgechromium", debug=False)
    finally:
        log("Jarvis desktop window closed")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        main()
    except Exception:
        log(traceback.format_exc())
        if "--smoke-test" in sys.argv:
            hard_exit(1)
        raise
