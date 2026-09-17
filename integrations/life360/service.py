"""In-memory Life360 shared-location session and God's Eye handoff."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.gods_eye_bridge import GodsEyeBridge

from .shared_link import Life360Location, Life360SharedLinkReader, validate_shared_link


@dataclass(slots=True)
class _MemberSession:
    alias: str
    share_url: str
    location: Life360Location | None = None


class Life360Service:
    """Manage explicitly supplied Life360 sharing links for the current process only."""

    def __init__(self, reader: Life360SharedLinkReader | None = None, bridge: GodsEyeBridge | None = None):
        self._reader = reader or Life360SharedLinkReader()
        self._bridge = bridge or GodsEyeBridge.from_environment()
        self._members: dict[str, _MemberSession] = {}

    def add_shared_link(self, alias: str, share_url: str) -> dict[str, Any]:
        safe_alias = alias.strip()
        if not safe_alias:
            raise ValueError("alias cannot be empty")
        safe_url = validate_shared_link(share_url)
        self._members[safe_alias] = _MemberSession(alias=safe_alias, share_url=safe_url)
        return {"success": True, "alias": safe_alias, "has_shared_link": True}

    def remove(self, alias: str) -> bool:
        return self._members.pop(alias.strip(), None) is not None

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(self._members),
            "members": [
                {
                    "alias": member.alias,
                    "has_shared_link": True,
                    "has_location": member.location is not None,
                }
                for member in self._members.values()
            ],
            "storage": "memory_only",
            "auth_model": "user_supplied_life360_share_link",
        }

    def refresh(self, alias: str) -> Life360Location:
        key = alias.strip()
        member = self._members.get(key)
        if member is None:
            raise KeyError(f"No Life360 shared link configured for '{key}'")
        location = self._reader.read(member.share_url, alias=member.alias)
        member.location = location
        return location

    def track(self, alias: str) -> dict[str, Any]:
        location = self.refresh(alias)
        request = self._bridge.capability(
            "track_object",
            alias=location.alias,
            name=location.name,
            latitude=location.latitude,
            longitude=location.longitude,
            accuracy_m=location.accuracy_m,
            battery_pct=location.battery_pct,
            updated_at=location.updated_at,
            source=location.source,
            follow=True,
        )
        return {
            "success": True,
            "location": location.as_dict(),
            "gods_eye": request,
            "gods_eye_url": self._bridge.location_url(location.latitude, location.longitude, zoom=15),
        }

    def get_cached(self, alias: str) -> Life360Location | None:
        member = self._members.get(alias.strip())
        return member.location if member else None


_default_service = Life360Service()


def get_family_location_service() -> Life360Service:
    """Return the process-local service shared by the API and built-in tools."""
    return _default_service
