import os

import pytest

import desktop.api_server as api_server
from desktop import provider_credentials


def test_provider_storage_round_trip_without_exposing_plaintext(monkeypatch, tmp_path):
    monkeypatch.setattr(provider_credentials, "_store_path", lambda: tmp_path / "credentials.json")
    if os.name == "nt":
        provider_credentials.save_key("openai", "test-secret")
        assert provider_credentials.get_key("openai") == "test-secret"
        raw = (tmp_path / "credentials.json").read_text(encoding="utf-8")
        assert "test-secret" not in raw
    else:
        with pytest.raises(RuntimeError):
            provider_credentials.save_key("openai", "test-secret")


@pytest.mark.asyncio
async def test_provider_api_contract(monkeypatch):
    saved = {}

    def fake_save(provider, api_key):
        saved[provider] = api_key

    def fake_delete(provider):
        saved.pop(provider, None)

    def fake_status():
        return [
            {"id": name, "env_var": env, "configured": name in saved}
            for name, env in provider_credentials.PROVIDERS.items()
        ]

    monkeypatch.setattr(api_server, "save_key", fake_save)
    monkeypatch.setattr(api_server, "delete_key", fake_delete)
    monkeypatch.setattr(api_server, "public_status", fake_status)

    client = api_server.app.test_client()

    response = await client.get("/api/v1/providers")
    assert response.status_code == 200
    assert (await response.get_json())["providers"][0]["configured"] is False

    response = await client.post(
        "/api/v1/providers",
        json={"provider": "openai", "api_key": "test-secret"},
    )
    assert response.status_code == 200
    assert saved["openai"] == "test-secret"
    assert "test-secret" not in await response.get_data(as_text=True)

    response = await client.get("/api/v1/providers")
    payload = await response.get_json()
    openai = next(item for item in payload["providers"] if item["id"] == "openai")
    assert openai["configured"] is True
    assert "api_key" not in openai

    response = await client.delete("/api/v1/providers/openai")
    assert response.status_code == 200
    assert "openai" not in saved
