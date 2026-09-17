from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


def _headers() -> dict[str, str]:
    return {"X-API-Key": "test-secret"}


@pytest.fixture
def api(monkeypatch):
    import desktop.api_server as module

    monkeypatch.setattr(module, "_API_SECRET", "test-secret")
    return module


async def test_life360_status_endpoint_exists(api):
    async with api.app.test_client() as client:
        response = await client.get("/api/v1/family/location", headers=_headers())
    assert response.status_code == 200
    data = await response.get_json()
    assert data["configured"] is False


async def test_life360_configure_endpoint_requires_https_life360_share_link(api):
    async with api.app.test_client() as client:
        response = await client.post(
            "/api/v1/family/location/configure",
            json={"alias": "alex", "share_url": "https://example.com/share/x"},
            headers=_headers(),
        )
    assert response.status_code == 422


async def test_life360_configure_and_remove(api):
    async with api.app.test_client() as client:
        configured = await client.post(
            "/api/v1/family/location/configure",
            json={"alias": "alex", "share_url": "https://share.life360.com/share/x"},
            headers=_headers(),
        )
        status = await client.get("/api/v1/family/location", headers=_headers())
        removed = await client.delete("/api/v1/family/location/alex", headers=_headers())

    assert configured.status_code == 200
    assert (await configured.get_json())["alias"] == "alex"
    data = await status.get_json()
    assert data["members"][0]["alias"] == "alex"
    assert removed.status_code == 200
