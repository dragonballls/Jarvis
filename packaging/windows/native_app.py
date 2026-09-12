from __future__ import annotations

import json
import os
import queue
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from urllib.request import Request, urlopen

from packaging.windows.app import (
    API_HOST,
    API_PORT,
    _auto_update_loop,
    install_startup,
    log,
    prepare_self_coding_workspace,
    run_api_server_thread,
    wait_for_port,
)


def _post_autopilot(goal: str, workspace: Path | None) -> None:
    payload = json.dumps({
        "goal": goal,
        "workspace": str(workspace) if workspace else None,
        "session_id": "jarvis-native",
    }).encode("utf-8")
    req = Request(
        f"http://{API_HOST}:{API_PORT}/api/v1/autopilot",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=900) as response:
            for line in response:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line.decode("utf-8", errors="replace"))
                    content = str(event.get("content", ""))
                    if content:
                        log(f"SELF-CODING: {content}")
                except json.JSONDecodeError:
                    log("SELF-CODING: " + line.decode("utf-8", errors="replace").strip())
    except Exception:
        log("Self-coding startup task failed:\n" + traceback.format_exc())


def _post_chat(message: str, session_id: str) -> list[str]:
    payload = json.dumps({
        "message": message,
        "session_id": session_id,
    }).encode("utf-8")
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
    workspace = prepare_self_coding_workspace()
    os.environ["JARVIS_WORKSPACE"] = str(workspace)
    install_startup()
    run_api_server_thread()
    wait_for_port(API_HOST, API_PORT, timeout=30.0)

    threading.Thread(
        target=_auto_update_loop,
        args=(workspace,),
        name="jarvis-auto-update",
        daemon=True,
    ).start()

    # Start autonomous self-coding only after the API is actually listening.
    threading.Thread(
        target=_post_autopilot,
        args=(
            "Begin autonomous self-coding. Inspect the Jarvis repository, choose the highest-value safe improvements, implement them, run tests and verification, preserve prior work, commit valid changes to GitHub main when verification passes, and continue improving the system safely.",
            workspace,
        ),
        name="jarvis-self-coding",
        daemon=True,
    ).start()

    log("Jarvis native desktop UI ready; autonomous self-coding started")
    run_native_ui(workspace)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(traceback.format_exc())
        raise
