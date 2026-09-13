from __future__ import annotations

import ctypes
import json
import os
import traceback
from pathlib import Path
from urllib.request import Request, urlopen

# Keep heavyweight runtime imports out of module import time. This lets the
# packaged executable create a diagnostic log before loading the API stack.
API_HOST = "127.0.0.1"
API_PORT = 8080
_auto_update_loop = None
install_startup = None
log = None
prepare_self_coding_workspace = None
run_api_server_thread = None
wait_for_port = None


def _bootstrap_log(message: str) -> None:
    """Write an early diagnostic line before the runtime module is imported."""
    paths = []
    try:
        paths.append(Path(sys.executable).resolve().parent / "jarvis.log")
    except Exception:
        pass
    try:
        paths.append(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Jarvis" / "jarvis.log")
    except Exception:
        pass
    line = message.rstrip() + "\n"
    for path in paths:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
            return
        except OSError:
            continue


def _load_runtime() -> None:
    global API_HOST, API_PORT, _auto_update_loop, install_startup, log
    global prepare_self_coding_workspace, run_api_server_thread, wait_for_port
    _bootstrap_log("Jarvis runtime bootstrap: loading packaging.windows.app")
    from packaging.windows import app as runtime

    API_HOST = runtime.API_HOST
    API_PORT = runtime.API_PORT
    _auto_update_loop = runtime._auto_update_loop
    install_startup = runtime.install_startup
    log = runtime.log
    prepare_self_coding_workspace = runtime.prepare_self_coding_workspace
    run_api_server_thread = runtime.run_api_server_thread
    wait_for_port = runtime.wait_for_port
    _bootstrap_log("Jarvis runtime bootstrap: packaging.windows.app loaded")


_MUTEX_HANDLE = None


def _acquire_single_instance() -> bool:
    global _MUTEX_HANDLE
    if os.name != "nt":
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, "Local\\Jarvis.Native.SingleInstance")
    if not handle:
        return True
    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(handle)
        return False
    _MUTEX_HANDLE = handle
    return True


def smoke_test() -> None:
    """Run a fast packaged-runtime check without opening the user interface."""
    log("Jarvis smoke test starting")
    run_api_server_thread()
    wait_for_port(API_HOST, API_PORT, timeout=30.0)
    request = Request(f"http://{API_HOST}:{API_PORT}/api/v1/health", method="GET")
    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "ok" or payload.get("name") != "Jarvis":
        raise RuntimeError(f"Unexpected health response: {payload}")
    log("SMOKE: API health OK")
    log("Jarvis smoke test passed")


def _post_autopilot(goal: str, workspace: Path | None) -> None:
    if workspace is None:
        log("Self-coding stopped: workspace is unavailable")
        return
    try:
        from agent.evolution import run_evolution_cycle

        for event in run_evolution_cycle(workspace, goal):
            content = str(event.get("content") or event.get("error") or event.get("output") or "")
            if content:
                log(f"SELF-CODING: {content.rstrip()}")
            if event.get("event"):
                log(f"SELF-CODING EVENT: {event}")
    except Exception:
        log("Self-coding startup task failed:\n" + traceback.format_exc())


def _post_chat(message: str, session_id: str) -> list[str]:
    payload = json.dumps({"message": message, "session_id": session_id}).encode("utf-8")
    req = Request(
        f"http://{API_HOST}:{API_PORT}/api/v1/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    chunks: list[str] = []
    with urlopen(req, timeout=300) as response:
        for line in response:
            if not line.strip():
                continue
            try:
                event = json.loads(line.decode("utf-8", errors="replace"))
                content = str(event.get("content", ""))
                if content:
                    chunks.append(content)
            except json.JSONDecodeError:
                continue
    return chunks


def run_native_ui(workspace: Path) -> None:
    import queue
    import tkinter as tk
    import threading
    from tkinter import font as tkfont

    events: queue.Queue[tuple[str, object]] = queue.Queue()
    root = tk.Tk()
    root.title("Jarvis")
    root.geometry("900x150")
    root.minsize(520, 110)
    root.configure(bg="#111111")

    text_font = tkfont.Font(family="Segoe UI", size=11)
    response_font = tkfont.Font(family="Segoe UI", size=10)

    status = tk.StringVar(value="Jarvis online — self-coding active")
    entry = tk.Entry(
        root,
        bg="#181818",
        fg="#f5f5f5",
        insertbackground="#f5f5f5",
        relief="flat",
        font=text_font,
    )
    entry.pack(fill="x", padx=18, pady=(18, 8), ipady=10)

    output = tk.Label(
        root,
        textvariable=status,
        bg="#111111",
        fg="#bcbcbc",
        anchor="w",
        justify="left",
        font=response_font,
    )
    output.pack(fill="x", padx=18, pady=(0, 12))

    session_id = "jarvis-native"

    def submit(_event=None) -> None:
        message = entry.get().strip()
        if not message:
            return
        entry.delete(0, "end")
        status.set("Jarvis is thinking…")

        def worker() -> None:
            try:
                chunks = _post_chat(message, session_id)
                events.put(("response", "".join(chunks).strip() or "Done."))
            except Exception as exc:
                events.put(("error", str(exc)))

        threading.Thread(target=worker, name="jarvis-chat", daemon=True).start()

    entry.bind("<Return>", submit)
    entry.focus_set()

    def poll() -> None:
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "response":
                    status.set(str(value))
                else:
                    status.set("Error: " + str(value))
        except queue.Empty:
            pass
        root.after(100, poll)

    def on_close() -> None:
        log("Jarvis desktop window closed")
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(100, poll)
    root.mainloop()


def main() -> None:
    _load_runtime()
    if "--smoke-test" in os.sys.argv:
        smoke_test()
        return
    if not _acquire_single_instance():
        return
    workspace = prepare_self_coding_workspace()
    os.environ["JARVIS_WORKSPACE"] = str(workspace)
    install_startup()
    run_api_server_thread()
    wait_for_port(API_HOST, API_PORT, timeout=30.0)

    import threading

    threading.Thread(
        target=_auto_update_loop,
        args=(workspace,),
        name="jarvis-auto-update",
        daemon=True,
    ).start()

    threading.Thread(
        target=_post_autopilot,
        args=(
            "Begin autonomous self-coding. Inspect the Jarvis repository, choose the highest-value safe improvement, implement it, run focused and relevant verification, preserve prior work, and only record verified changes. Keep every integration and future addition in its own isolated component boundary while allowing narrow interfaces between components.",
            workspace,
        ),
        name="jarvis-self-coding",
        daemon=True,
    ).start()

    log("Jarvis native desktop UI ready; guarded autonomous coding started")
    run_native_ui(workspace)


if __name__ == "__main__":
    try:
        import sys
        if "--smoke-test" in sys.argv:
            _bootstrap_log("Jarvis smoke-test bootstrap starting")
        main()
    except Exception:
        _bootstrap_log("Jarvis native app failed during bootstrap:\n" + traceback.format_exc())
        if log is not None:
            log(traceback.format_exc())
        raise
