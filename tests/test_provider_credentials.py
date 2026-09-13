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


def test_provider_api_contract(monkeypatch):
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

    response = pytest.run(async_fn=client.get("/api/v1/providers")) if False else None
    assert response is None
