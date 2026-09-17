"""Tests for the minimal Jarvis API server (desktop/api_server.py).

The server exposes conversation, self-coding autopilot, provider settings, voice,
and the consent-based family-location integration while retaining the minimal
runtime boundary and authentication checks.
"""

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def api(monkeypatch):
    import desktop.api_server as module

    monkeypatch.setattr(module, "_API_SECRET", "test-secret")
    module._agents.clear()
    return module


@pytest.fixture
def app(api):
    return api.app


@pytest.fixture
def headers():
    return {"X-API-Key": "test-secret"}


class TestHealth:
    async def test_health_ok(self, app):
        async with app.test_client() as client:
            resp = await client.get("/api/v1/health")
            data = await resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "ok"
        assert data["mode"] == "minimal"
        assert data["features"] == [
            "conversation",
            "self_coding",
            "provider_settings",
            "voice",
            "openhands",
            "emrg_evolution",
            "family_location",
        ]
        assert data["name"] == "Jarvis"

    async def test_health_does_not_require_auth(self, app):
        async with app.test_client() as client:
            resp = await client.get("/api/v1/health")
        assert resp.status_code == 200


class TestAuth:
    async def test_chat_rejects_missing_key(self, app):
        async with app.test_client() as client:
            resp = await client.post("/api/v1/chat", json={"message": "hello"})
        assert resp.status_code == 401

    async def test_chat_rejects_wrong_key(self, app):
        async with app.test_client() as client:
            resp = await client.post(
                "/api/v1/chat", json={"message": "hello"}, headers={"X-API-Key": "wrong"}
            )
        assert resp.status_code == 401

    async def test_chat_accepts_correct_key(self, app, headers, monkeypatch):
        class FakeAgent:
            def run(self, message):
                yield {"type": "done", "content": f"reply:{message}", "final": True}

        monkeypatch.setattr("desktop.api_server.get_agent", lambda session_id="default": FakeAgent())
        async with app.test_client() as client:
            resp = await client.post("/api/v1/chat", json={"message": "hello"}, headers=headers)
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"


class TestChat:
    async def test_chat_requires_message(self, app, headers):
        async with app.test_client() as client:
            resp = await client.post("/api/v1/chat", json={}, headers=headers)
        assert resp.status_code == 422

    async def test_chat_rejects_empty_message(self, app, headers):
        async with app.test_client() as client:
            resp = await client.post("/api/v1/chat", json={"message": "   "}, headers=headers)
        assert resp.status_code == 422

    async def test_chat_rejects_non_string_message(self, app, headers):
        async with app.test_client() as client:
            resp = await client.post("/api/v1/chat", json={"message": 42}, headers=headers)
        assert resp.status_code == 422

    async def test_chat_rejects_oversized_message(self, app, headers):
        async with app.test_client() as client:
            resp = await client.post(
                "/api/v1/chat", json={"message": "x" * 10001}, headers=headers
            )
        assert resp.status_code == 422

    async def test_chat_streams_agent_events(self, app, headers, monkeypatch):
        class FakeAgent:
            def run(self, message):
                yield {"type": "delta", "content": f"reply:{message}"}
                yield {"type": "done", "content": "ok", "final": True}

        monkeypatch.setattr("desktop.api_server.get_agent", lambda session_id="default": FakeAgent())
        async with app.test_client() as client:
            resp = await client.post("/api/v1/chat", json={"message": "hello"}, headers=headers)
            body = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"
        assert "reply:hello" in body
        assert '"final": true' in body

    async def test_chat_streams_error_when_agent_crashes(self, app, headers, monkeypatch):
        class BoomAgent:
            def run(self, message):
                raise RuntimeError("boom")

        monkeypatch.setattr("desktop.api_server.get_agent", lambda session_id="default": BoomAgent())
        async with app.test_client() as client:
            resp = await client.post("/api/v1/chat", json={"message": "hello"}, headers=headers)
            body = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Error: boom" in body
        assert '"final": true' in body

    async def test_chat_session_isolation(self, app, headers, monkeypatch):
        runs: list[str] = []

        class FakeAgent:
            def run(self, message):
                runs.append(message)
                yield {"type": "done", "content": "ok", "final": True}

        monkeypatch.setattr("desktop.api_server.get_agent", lambda session_id="default": FakeAgent())
        async with app.test_client() as client:
            await client.post("/api/v1/chat", json={"message": "one"}, headers=headers)
            await client.post("/api/v1/chat", json={"message": "two"}, headers=headers)
        assert runs == ["one", "two"]


class TestAutopilot:
    async def test_requires_goal(self, app, headers):
        async with app.test_client() as client:
            resp = await client.post("/api/v1/autopilot", json={}, headers=headers)
        assert resp.status_code == 422

    async def test_rejects_blank_goal(self, app, headers):
        async with app.test_client() as client:
            resp = await client.post("/api/v1/autopilot", json={"goal": "  "}, headers=headers)
        assert resp.status_code == 422

    async def test_rejects_invalid_workspace(self, app, headers):
        async with app.test_client() as client:
            resp = await client.post(
                "/api/v1/autopilot",
                json={"goal": "improve Jarvis", "workspace": "../escape"},
                headers=headers,
            )
        assert resp.status_code == 422

    async def test_streams_self_coding_path(self, api, app, headers, monkeypatch):
        monkeypatch.setattr(api, "is_self_coding_goal", lambda goal: True)
        monkeypatch.setattr(
            api,
            "run_coding_agent",
            lambda workspace, goal: iter(
                [
                    {"type": "autopilot", "event": "plan", "goal": goal},
                    {"type": "done", "content": "completed", "final": True},
                ]
            ),
        )
        async with app.test_client() as client:
            resp = await client.post(
                "/api/v1/autopilot",
                json={"goal": "improve itself", "workspace": "/tmp/workspace"},
                headers=headers,
            )
            body = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"
        assert '"event": "plan"' in body
        assert '"final": true' in body

    async def test_streams_regular_autopilot_path(self, api, app, headers, monkeypatch):
        class FakeAutopilotAgent:
            def run_autopilot(self, goal, workspace):
                yield {"type": "progress", "content": goal}
                yield {"type": "done", "content": "finished", "final": True}

        monkeypatch.setattr(api, "is_self_coding_goal", lambda goal: False)
        monkeypatch.setattr(api, "get_agent", lambda session_id="default": FakeAutopilotAgent())
        async with app.test_client() as client:
            resp = await client.post(
                "/api/v1/autopilot",
                json={"goal": "greet me", "workspace": "/tmp/workspace"},
                headers=headers,
            )
            body = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert '"content": "greet me"' in body
        assert "finished" in body

    async def test_streams_error_when_self_coding_crashes(self, api, app, headers, monkeypatch):
        def crash(workspace, goal):
            raise RuntimeError("autopilot failure")

        monkeypatch.setattr(api, "is_self_coding_goal", lambda goal: True)
        monkeypatch.setattr(api, "run_coding_agent", crash)
        async with app.test_client() as client:
            resp = await client.post(
                "/api/v1/autopilot",
                json={"goal": "improve itself", "workspace": "/tmp/workspace"},
                headers=headers,
            )
            body = await resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Self-coding error: autopilot failure" in body
        assert '"final": true' in body


class TestMinimalSurface:
    async def test_disabled_endpoint_returns_404(self, app, headers):
        async with app.test_client() as client:
            resp = await client.get("/api/v1/sessions", headers=headers)
            data = await resp.get_json()
        assert resp.status_code == 404
        assert data["error"] == "Disabled in minimal Jarvis mode"

    async def test_disabled_endpoint_is_safe_without_auth(self, app):
        async with app.test_client() as client:
            resp = await client.get("/api/v1/sessions")
        assert resp.status_code == 404

    async def test_options_preflight(self, app):
        async with app.test_client() as client:
            resp = await client.options(
                "/api/v1/chat",
                headers={
                    "Origin": "http://127.0.0.1:5173",
                    "Access-Control-Request-Method": "POST",
                },
            )
        assert resp.status_code == 200


async def test_validation_helpers():
    import desktop.api_server as api

    assert api.validate_chat_input({}) == "message cannot be empty"
    assert api.validate_chat_input({"message": 1}) == "message must be a string"
    assert api.validate_chat_input({"message": "ok"}) is None
    assert api.validate_workspace(None) is None
    assert api.validate_workspace("/safe") is None
    assert api.validate_workspace("../escape") == "invalid workspace path"
    assert api.validate_workspace("~/x") == "invalid workspace path"
