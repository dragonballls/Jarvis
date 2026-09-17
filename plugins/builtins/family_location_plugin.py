"""Jarvis family-location tools backed by user-authorized Life360 share links."""

from __future__ import annotations

from typing import Any

from integrations.life360.service import get_family_location_service
from plugins.base import ToolPlugin


_SERVICE = get_family_location_service()


class FamilyLocationConfigurePlugin(ToolPlugin):
    name = "family_location_configure"
    description = "Save a user-provided official Life360 shared-location link for a family member. The link is kept in memory only and never returned or logged."
    category = "family"

    def get_parameters_schema(self):
        return {
            "type": "object",
            "properties": {
                "alias": {"type": "string", "description": "A local nickname such as mom, dad, or sister."},
                "share_url": {"type": "string", "description": "An HTTPS Life360 sharing link created by the person sharing their location."},
            },
            "required": ["alias", "share_url"],
        }

    def execute(self, alias: str, share_url: str) -> dict[str, Any]:
        return _SERVICE.add_shared_link(alias, share_url)


class FamilyLocationStatusPlugin(ToolPlugin):
    name = "family_location_status"
    description = "List configured family-location aliases without revealing their Life360 links."
    category = "family"

    def get_parameters_schema(self):
        return {"type": "object", "properties": {}, "required": []}

    def execute(self) -> dict[str, Any]:
        return _SERVICE.status()


class FamilyLocationPlugin(ToolPlugin):
    name = "family_location"
    description = "Refresh the authorized Life360 shared location for one configured family member."
    category = "family"

    def get_parameters_schema(self):
        return {
            "type": "object",
            "properties": {"alias": {"type": "string", "description": "Configured family-member alias."}},
            "required": ["alias"],
        }

    def execute(self, alias: str) -> dict[str, Any]:
        location = _SERVICE.refresh(alias)
        return {"success": True, "location": location.as_dict()}


class FamilyLocationTrackPlugin(ToolPlugin):
    name = "family_location_track"
    description = "Refresh a configured Life360 family member and return a God's Eye track request plus map URL."
    category = "family"

    def get_parameters_schema(self):
        return {
            "type": "object",
            "properties": {"alias": {"type": "string", "description": "Configured family-member alias."}},
            "required": ["alias"],
        }

    def execute(self, alias: str) -> dict[str, Any]:
        return _SERVICE.track(alias)


class FamilyLocationRemovePlugin(ToolPlugin):
    name = "family_location_remove"
    description = "Forget a configured family-member Life360 share link from the current Jarvis process."
    category = "family"

    def get_parameters_schema(self):
        return {
            "type": "object",
            "properties": {"alias": {"type": "string", "description": "Configured family-member alias."}},
            "required": ["alias"],
        }

    def execute(self, alias: str) -> dict[str, Any]:
        removed = _SERVICE.remove(alias)
        return {"success": removed, "alias": alias.strip(), "removed": removed}


__all__ = [
    "FamilyLocationConfigurePlugin",
    "FamilyLocationStatusPlugin",
    "FamilyLocationPlugin",
    "FamilyLocationTrackPlugin",
    "FamilyLocationRemovePlugin",
    "get_family_location_service",
]
