import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def api(monkeypatch):
    import desktop.api_server as module

    monkeypatch.setattr(module, "_API_SECRET", "test-secret")
    module._agents.clear()
    return module


@pytest.fixture
def headers():
    return {"X-API-Key": "test-secret"}


class TestHealth:
    async def test_health_ok(self, api):
        async with api.app.test_client() as client:
            response = await client.get("/api/v1/health")
            data = await response.get_json()
        assert response.status_code == 200
        assert data["status"] == "ok"
        assert data["name"] == "Jarvis"
        assert data["features"] == ["conversation", "self_coding", "provider_settings", "voice", "openhands", "emrg_evolution", "family_location"]
        assert data["engines"]["opencode"] is True


class TestAuth:
    async def test_health_does_not_require_auth(self, api):
        async with api.app.test_client() as client:
            response = await client.get("/api/v1/health")
        assert response.status_code == 200

    async def test_chat_rejects_wrong_key(self, api):
        async with api.app.test_client() as client:
            response = await client.post(
                "/api/v1/chat", json={"message": "hello"}, headers={"X-API-Key": "wrong"}
            )
        assert response.status_code == 401


class TestChat:
    async def test_requires_message(self, api, headers):
        async with api.app.test_client() as client:
            response = await client.post("/api/v1/chat", json={}, headers=headers)
        assert response.status_code == 422

    async def test_rejects_empty_message(self, api, headers):
        async with api.app.test_client() as client:
            response = await client.post(
                "/api/v1/chat", json={"message": "   "}, headers=headers
            )
        assert response.status_code == 422

    async def test_rejects_oversized_message(self, api, headers):
        async with api.app.test_client() as client:
            response = await client.post(
                "/api/v1/chat", json={"message": "x" * 10001}, headers=headers
            )
        assert response.status_code == 422

    async def test_streams_agent_events(self, api, headers, monkeypatch):
        class FakeAgent:
            def run(self, message):
                yield {"type": "delta", "content": f"reply:{message}"}
                yield {"type": "done", "content": "ok", "final": True}

        monkeypatch.setattr(api, "get_agent", lambda session_id="default": FakeAgent())
        async with api.app.test_client() as client:
            response = await client.post(
                "/api/v1/chat", json={"message": "hello"}, headers=headers
            )
            body = await response.get_data(as_text=True)
        assert response.status_code == 200
        assert response.mimetype == "text/event-stream"
        assert "reply:hello" in body
        assert '"final": true' in body


class TestAutopilot:
    async def test_requires_goal(self, api, headers):
        async with api.app.test_client() as client:
            response = await client.post("/api/v1/autopilot", json={}, headers=headers)
        assert response.status_code == 422

    async def test_rejects_invalid_workspace(self, api, headers):
        async with api.app.test_client() as client:
            response = await client.post(
                "/api/v1/autopilot",
                json={"goal": "improve Jarvis", "workspace": "../escape"},
                headers=headers,
            )
        assert response.status_code == 422

    async def test_streams_self_coding_path(self, api, headers, monkeypatch):
        monkeypatch.setattr(api, "is_self_coding_goal", lambda goal: True)
        monkeypatch.setattr(
            api,
            "run_coding_agent",
            lambda workspace, goal: iter(
                [
                    {"type": "progress", "content": "started"},
                    {"type": "done", "content": "completed", "final": True},
                ]
            ),
        )
        async with api.app.test_client() as client:
            response = await client.post(
                "/api/v1/autopilot",
                json={"goal": "self-coding", "workspace": "/tmp/workspace"},
                headers=headers,
            )
            body = await response.get_data(as_text=True)
        assert response.status_code == 200
        assert response.mimetype == "text/event-stream"
        assert "started" in body
        assert "completed" in body

    async def test_self_coding_requires_workspace(self, api, headers, monkeypatch):
        monkeypatch.setattr(api, "is_self_coding_goal", lambda goal: True)
        monkeypatch.delenv("JARVIS_WORKSPACE", raising=False)
        monkeypatch.delenv("FRIDAY_WORKSPACE", raising=False)

        def unexpected(workspace, goal):
            raise AssertionError("run_coding_agent must not be called without a workspace")

        monkeypatch.setattr(api, "run_coding_agent", unexpected)
        async with api.app.test_client() as client:
            response = await client.post(
                "/api/v1/autopilot",
                json={"goal": "improve itself"},
                headers=headers,
            )
            body = await response.get_data(as_text=True)
        assert response.status_code == 200
        assert "requires an explicit workspace path" in body
        assert '"final": true' in body


class TestMinimalSurface:
    async def test_non_core_endpoint_returns_404(self, api, headers):
        async with api.app.test_client() as client:
            response = await client.get("/api/v1/sessions", headers=headers)
            data = await response.get_json()
        assert response.status_code == 404
        assert data["error"] == "Disabled in minimal Jarvis mode"

    async def test_options_preflight(self, api):
        async with api.app.test_client() as client:
            response = await client.options(
                "/api/v1/chat",
                headers={
                    "Origin": "http://127.0.0.1:5173",
                    "Access-Control-Request-Method": "POST",
                },
            )
        assert response.status_code == 200


async def test_validation_helpers():
    import desktop.api_server as api

    assert api.validate_chat_input({}) == "message cannot be empty"
    assert api.validate_chat_input({"message": 1}) == "message must be a string"
    assert api.validate_chat_input({"message": "ok"}) is None
    assert api.validate_workspace(None) is None
    assert api.validate_workspace("/safe") is None
    assert api.validate_workspace("../escape") == "invalid workspace path"
