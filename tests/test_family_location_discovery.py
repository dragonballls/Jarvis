from __future__ import annotations

from core import registry


def test_api_runtime_discovers_family_location_tools() -> None:
    # Importing the API server must initialize the same tool registry used by
    # packaged Jarvis; callers should not need to invoke CLI-only startup code.
    import desktop.api_server  # noqa: F401

    names = set(registry.get_tool_map())
    assert {
        "family_location_configure",
        "family_location_status",
        "family_location",
        "family_location_track",
        "family_location_remove",
    } <= names
