from main import _launch_ui, _repl_loop


def test_launch_ui_builds_commands(monkeypatch):
    """--ui should spawn the API server and frontend dev server, then open the browser."""
    spawned: list[list[str]] = []
    opened: list[str] = []
    sleep_count = 0

    class FakeProc:
        def __init__(self, cmd):
            self._cmd = cmd
            self._polls = 0
            self.returncode = 0

        def poll(self):
            self._polls += 1
            return None if self._polls < 3 else 0

        def terminate(self):
            self._terminated = True

    def fake_popen(cmd, **kwargs):
        spawned.append(cmd)
        return FakeProc(cmd)

    def fake_sleep(_secs):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count > 2:
            raise KeyboardInterrupt

    def fake_open(url):
        opened.append(url)

    monkeypatch.setattr("main._auto_update_monitor", lambda *_args: None)
    monkeypatch.setattr("main._wait_for_port", lambda *args, **kwargs: None)
    monkeypatch.setattr("main.subprocess.Popen", fake_popen)
    monkeypatch.setattr("main.time.sleep", fake_sleep)
    monkeypatch.setattr("main.webbrowser.open", fake_open)

    _launch_ui()

    assert len(spawned) == 2
    assert "api_server.py" in " ".join(spawned[0])
    assert any("dev" in str(c) for c in spawned[1])
    assert opened == ["http://127.0.0.1:5173/"]


def test_launch_ui_restarts_monitor_after_failed_update(monkeypatch):
    """A failed update must not permanently disable future update detection."""
    monitor_calls: list[int] = []
    spawned: list[list[str]] = []
    sleep_count = 0

    class FakeProc:
        def __init__(self, cmd):
            self._polls = 0
            self._cmd = cmd
            self.returncode = 0

        def poll(self):
            self._polls += 1
            return None if self._polls < 3 else 0

        def terminate(self):
            pass

    class FakeThread:
        starts: list["FakeThread"] = []

        def __init__(self, target, args, **_kwargs):
            self._target = target
            self._args = args

        def start(self):
            self.starts.append(self)
            if len(self.starts) == 1:
                self._target(*self._args)

    def fake_monitor(_root, update_event, _stop_event):
        monitor_calls.append(1)
        update_event.set()

    def fake_popen(cmd, **_kwargs):
        spawned.append(cmd)
        return FakeProc(cmd)

    def fake_sleep(_secs):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count > 6:
            raise KeyboardInterrupt

    monkeypatch.setattr("main.threading.Thread", FakeThread)
    monkeypatch.setattr("main._auto_update_monitor", fake_monitor)
    monkeypatch.setattr("main._wait_for_port", lambda *args, **kwargs: None)
    monkeypatch.setattr("main.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "main.subprocess.run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 4})(),
    )
    monkeypatch.setattr("main.time.sleep", fake_sleep)
    monkeypatch.setattr("main.webbrowser.open", lambda _url: None)

    _launch_ui()

    assert len(spawned) == 4
    assert len(monitor_calls) == 1
    assert len(FakeThread.starts) == 2


def test_launch_ui_recovers_when_child_process_stops(monkeypatch):
    """A dead API/frontend child should restart without stopping the updater monitor."""
    starts = 0
    monitor_starts = 0
    restart_seen = False

    class FakeProc:
        def __init__(self, alive_polls: int):
            self.polls = 0
            self.alive_polls = alive_polls
            self.terminated = False

        def poll(self):
            if self.terminated:
                return 0
            self.polls += 1
            return None if self.polls <= self.alive_polls else 1

        def terminate(self):
            self.terminated = True

    def fake_start(_desktop):
        nonlocal starts, restart_seen
        starts += 1
        if starts > 1:
            restart_seen = True
        if starts == 1:
            return [FakeProc(0), FakeProc(0)]
        return [FakeProc(10_000), FakeProc(10_000)]

    def fake_monitor(*_args):
        nonlocal monitor_starts
        monitor_starts += 1

    def fake_sleep(_secs):
        if restart_seen:
            raise KeyboardInterrupt

    monkeypatch.setattr("main._start_ui_processes", fake_start)
    monkeypatch.setattr("main._start_auto_update_monitor", fake_monitor)
    monkeypatch.setattr("main._auto_update_monitor", fake_monitor)
    monkeypatch.setattr("main.time.sleep", fake_sleep)
    monkeypatch.setattr("main.webbrowser.open", lambda _url: None)

    _launch_ui()

    assert starts == 2
    assert monitor_starts == 1


def test_repl_loop_survives_agent_error(monkeypatch):
    """A crashing agent run must not kill the CLI session."""
    inputs = iter(["hello", "/exit"])
    errors_seen: list[str] = []

    class FakeAgent:
        language = "english"

        def run(self, _user_input):
            raise RuntimeError("provider exploded")

        def resolve_approval(self, request_id, allowed):
            return True

        def clear(self):
            pass

        def set_language(self, lang):
            self.language = lang

    monkeypatch.setattr("builtins.input", lambda _prompt: next(inputs))
    monkeypatch.setattr(
        "main.print_colored",
        lambda text, _color="37": errors_seen.append(text) if "Error while processing your request" in text else None,
    )

    _repl_loop(FakeAgent())

    assert len(errors_seen) == 1
    assert "provider exploded" in errors_seen[0]
