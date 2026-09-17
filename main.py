import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

from agent.core import Agent
from core.registry import discover_plugins
from voice import is_voice_available, listen, speak

BANNER = r"""
  _____  _     _     _
 |  ___(_) __| |_   _| | ___
 | |_  | |/ _` | | | | |/ _ \
 |  _| | | (_| | |_| | |  __/
 |_|   |_|\__,_|\__,_| |\___|
                |___/
"""
LANG_LABELS = {"english": "English", "hinglish": "Hinglish"}
AUTO_UPDATE_INTERVAL = 60


def get_terminal_width() -> int:
    return shutil.get_terminal_size((80, 20)).columns


def print_colored(text: str, color_code: str = "37"):
    print(f"\033[{color_code}m{text}\033[0m")


def _auto_update_monitor(root: str, update_event: threading.Event, stop_event: threading.Event):
    """Watch origin/main while the UI supervisor is alive."""
    raw_interval = os.environ.get("FRIDAY_AUTO_UPDATE_INTERVAL", str(AUTO_UPDATE_INTERVAL))
    try:
        interval = max(15, int(raw_interval))
    except ValueError:
        interval = AUTO_UPDATE_INTERVAL
    first_check = True
    while not stop_event.is_set():
        if not first_check and stop_event.wait(interval):
            return
        first_check = False
        try:
            branch = subprocess.run(
                ["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True, timeout=15, check=False
            ).stdout.strip()
            if branch != "main":
                continue
            status = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if status.returncode != 0 or status.stdout.strip():
                continue
            fetch = subprocess.run(
                ["git", "fetch", "origin", "main", "--prune"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if fetch.returncode != 0:
                continue
            local = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=15, check=False
            ).stdout.strip()
            remote = subprocess.run(
                ["git", "rev-parse", "origin/main"], cwd=root, capture_output=True, text=True, timeout=15, check=False
            ).stdout.strip()
            if local and remote and local != remote:
                update_event.set()
                return
        except (OSError, subprocess.SubprocessError, ValueError):
            continue


def _start_auto_update_monitor(root: str, update_event: threading.Event, stop_event: threading.Event):
    monitor = threading.Thread(
        target=_auto_update_monitor, args=(root, update_event, stop_event), name="friday-auto-updater", daemon=True
    )
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


def _wait_for_port(host: str, port: int, proc: subprocess.Popen, timeout: float = 30.0) -> None:
    """Wait until a child service accepts connections, or fail with its exit code."""
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"Friday UI service exited before port {port} became ready (exit code {proc.returncode})."
            )
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Friday UI service did not become ready on {host}:{port} within {timeout:.0f}s ({last_error}).")


def _start_ui_processes(desktop: str) -> list[subprocess.Popen]:
    api_cmd = [sys.executable, os.path.join(desktop, "api_server.py")]
    if sys.platform == "win32":
        npm_cmd = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm_cmd:
            raise RuntimeError("npm was not found on PATH; cannot start the Friday frontend.")
        # Vite may resolve localhost to IPv6 (::1) on Windows. Bind explicitly to
        # IPv4 so the readiness probe and browser use the same reachable endpoint.
        front_cmd = [npm_cmd, "run", "dev", "--", "--host", "127.0.0.1"]
    else:
        front_cmd = ["npm", "run", "dev", "--", "--host", "127.0.0.1"]

    procs: list[subprocess.Popen] = []
    try:
        api = subprocess.Popen(api_cmd, cwd=desktop)
        procs.append(api)
        _wait_for_port("127.0.0.1", 8080, api)

        front = subprocess.Popen(front_cmd, cwd=desktop)
        procs.append(front)
        _wait_for_port("127.0.0.1", 5173, front)
        return procs
    except Exception:
        _terminate_processes(procs)
        raise


def _open_ui_browser():
    """Open the actual Vite frontend, not the API's default port."""
    url = "http://127.0.0.1:5173/"
    print_colored(f"Friday UI ready — opening {url}", "32")
    webbrowser.open(url)


def _launch_ui():
    """Launch the UI and keep its source/runtime synchronized with origin/main."""
    root = os.path.dirname(os.path.abspath(__file__))
    desktop = os.path.join(root, "desktop")
    print_colored(BANNER, "36")
    print_colored("─" * get_terminal_width(), "90")
    print_colored("Launching Friday desktop UI…  (Ctrl+C to stop everything)", "33")
    print_colored("─" * get_terminal_width(), "90")
    update_event = threading.Event()
    stop_event = threading.Event()
    _start_auto_update_monitor(root, update_event, stop_event)
    procs: list[subprocess.Popen] = []
    try:
        procs = _start_ui_processes(desktop)
        _open_ui_browser()
        while True:
            time.sleep(1.0)
            if update_event.is_set():
                print_colored("\nFriday update detected — restarting safely…", "33")
                _terminate_processes(procs)
                procs.clear()
                result = subprocess.run(
                    [sys.executable, os.path.join(root, "scripts", "update.py"), "--build"], cwd=root, check=False
                )
                if result.returncode == 0:
                    stop_event.set()
                    os.execv(sys.executable, [sys.executable, *sys.argv])
                print_colored(
                    "Update could not be fully applied; restarting Friday on the latest source available.", "31"
                )
                update_event.clear()
                stop_event.clear()
                _start_auto_update_monitor(root, update_event, stop_event)
                procs = _start_ui_processes(desktop)
                _open_ui_browser()
            elif any(p.poll() is not None for p in procs):
                print_colored(
                    "\nFriday UI process stopped — restarting the UI while keeping update monitoring active.", "33"
                )
                _terminate_processes(procs)
                procs.clear()
                time.sleep(2.0)
                procs = _start_ui_processes(desktop)
                _open_ui_browser()
    except KeyboardInterrupt:
        print_colored("\nShutting down Friday UI…", "33")
    except RuntimeError as exc:
        print_colored(f"\nFriday UI startup failed: {exc}", "31")
    finally:
        stop_event.set()
        _terminate_processes(procs)


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="Friday — AI Assistant")
    parser.add_argument(
        "--lang", choices=["english", "hinglish"], default="english", help="Language (default: english)"
    )
    parser.add_argument(
        "--no-confirm", action="store_true", help="Skip confirmation prompts for destructive tool calls"
    )
    parser.add_argument(
        "--ui", action="store_true", help="Launch the full desktop UI (API server + frontend dev server)"
    )
    args = parser.parse_args()
    if args.ui:
        _launch_ui()
        return
    lang = args.lang
    label = LANG_LABELS.get(lang, "English")
    print_colored(BANNER, "36")
    print_colored("─" * get_terminal_width(), "90")
    print_colored(f"Friday — {label} AI Assistant (Ctrl+C to exit, /help for commands)", "33")
    print_colored("─" * get_terminal_width(), "90")
    print()
    discover_plugins()
    agent = Agent(language=lang, confirm_enabled=not args.no_confirm)
    try:
        _repl_loop(agent)
    finally:
        try:
            from browser import close_browser
        except ImportError:
            return
        close_browser()


def _repl_loop(agent: Agent):
    while True:
        try:
            user_input = input("\033[32m❯\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print_colored("Bye bye! 👋", "33")
            sys.exit(0)
        if not user_input:
            continue
        if user_input.startswith("/"):
            handled = _handle_command(user_input, agent)
            if handled == "exit":
                break
            continue
        print()
        try:
            for event in agent.run(user_input):
                if event["type"] == "tokens":
                    print(event["content"], end="", flush=True)
                elif event["type"] == "requires_confirmation":
                    print_colored(f"  ⚠ Tool '{event['tool']}' requires confirmation:", "33")
                    print_colored(f"     Args: {event.get('args') or '{}'}", "90")
                    while True:
                        try:
                            answer = input("\033[33m  Allow? [y/N]\033[0m ").strip().lower()
                        except (EOFError, KeyboardInterrupt):
                            answer = "n"
                        if answer in ("y", "yes"):
                            agent.resolve_approval(event["request_id"], True)
                            break
                        if answer in ("n", "no", ""):
                            agent.resolve_approval(event["request_id"], False)
                            break
                elif event["type"] == "tool_result":
                    for t in event.get("tools", []):
                        print_colored(f"  🛠 {t['name']}({t['args']})", "90")
                        print_colored(f"     Result: {t['result']}", "90")
        except Exception as exc:
            print_colored(f"  ⚠ Error while processing your request: {exc}", "31")
            print("Nothing was lost — your conversation continues. Try again or use /clear.", "90")
        print("\n")


def _voice_loop(agent: Agent):
    if not is_voice_available():
        print_colored("Voice not available — no microphone detected. Install pyaudio for voice support.", "31")
        return
    print_colored("Voice mode active. Speak now. Say 'exit' or press Ctrl+C to return to text mode.", "33")
    print_colored("Listening...", "33")
    while True:
        try:
            result = listen()
            if not result.get("success"):
                if "timeout" in result.get("error", ""):
                    print_colored("Listening... (no speech detected, keep talking or say 'exit')", "33")
                    continue
                print_colored(f"STT error: {result.get('error')}", "31")
                continue
            text = result["text"].strip().lower()
            print_colored(f"\nYou (voice): {result['text']}", "90")
            if text in ("exit", "exit voice", "band karo", "stop"):
                print_colored("Exiting voice mode.", "33")
                return
            print()
            full_response = ""
            for event in agent.run(result["text"]):
                if event["type"] == "tokens":
                    full_response += event["content"]
                    print(event["content"], end="", flush=True)
                elif event["type"] == "tool_result":
                    for t in event.get("tools", []):
                        print_colored(f"  🛠 {t['name']}({t['args']})", "90")
                        print_colored(f"     Result: {t['result']}", "90")
            if full_response.strip():
                speak(full_response)
            print_colored("\n\nListening...", "33")
        except KeyboardInterrupt:
            print()
            return
        except Exception as e:
            print_colored(f"Voice error: {e}", "31")
            return


def _handle_command(cmd: str, agent: Agent):
    cmd = cmd.lower().strip()
    if cmd in ("/exit", "/quit"):
        print_colored("Bye bye! 👋", "33")
        return "exit"
    elif cmd == "/clear":
        agent.clear()
        print_colored(
            "Conversation cleared! ✅" if agent.language == "english" else "Baat-cheet clear ho gayi! ✅", "33"
        )
    elif cmd == "/voice":
        _voice_loop(agent)
    elif cmd.startswith("/lang"):
        parts = cmd.split()
        if len(parts) == 1:
            current = LANG_LABELS.get(agent.language, agent.language)
            print_colored(f"Current language: {current}. Usage: /lang english or /lang hinglish", "33")
        else:
            target = parts[1]
            if target in ("english", "en"):
                agent.set_language("english")
                print_colored("Switched to English 🇬🇧", "33")
            elif target in ("hinglish", "hi", "hindi"):
                agent.set_language("hinglish")
                print_colored("Hinglish mein switch ho gaya 🇮🇳", "33")
            else:
                print_colored(f"Unknown language: {target}. Use: english or hinglish", "31")
    elif cmd in ("/help", "/?"):
        _print_help(agent.language)
    else:
        print_colored(f"Unknown: {cmd}. Type /help for commands.", "31")


def _print_help(lang: str):
    if lang == "english":
        print_colored(
            """
Commands:
  /help               Show this help
  /clear              Reset conversation
  /voice              Enter voice mode (speak, assistant responds)
  /lang <language>    Switch language: english or hinglish
  /exit               Quit

The assistant has tools for:
  - Shell commands, file operations, web fetching
  - Browser automation (navigate, click, type, screenshot)
  - Python code execution
  - Persistent memory (remember/recall)
  - File/content search
  - System information
""",
            "33",
        )
    else:
        print_colored(
            """
Commands:
  /help               Yeh help message
  /clear              Baat-cheet reset karo
  /voice              Voice mode mein jao (bolo, assistant jawab dega)
  /lang <language>    Language badlo: english ya hinglish
  /exit               Band karo

Assistant ke paas tools hain:
  - Shell commands, file operations, web fetching
  - Browser automation (navigate, click, type, screenshot)
  - Python code execution
  - Persistent memory (remember/recall)
  - File search
  - System information
""",
            "33",
        )


if __name__ == "__main__":
    main()
