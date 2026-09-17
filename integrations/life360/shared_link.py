"""Safe reader for official Life360 shared-location pages.

Jarvis does not log in to Life360, bypass access controls, call private APIs, or
store a Circle credential. A user supplies an official HTTPS Life360 sharing
link that already grants access to the shared location.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse


_MAX_ALIAS_LENGTH = 80
_LIFE360_HOST_SUFFIX = ".life360.com"


@dataclass(frozen=True, slots=True)
class Life360Location:
    alias: str
    latitude: float
    longitude: float
    name: str | None = None
    accuracy_m: float | None = None
    battery_pct: int | None = None
    updated_at: str | None = None
    source: str = "life360_shared_location"

    def as_dict(self) -> dict[str, object | None]:
        return {
            "alias": self.alias,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy_m": self.accuracy_m,
            "battery_pct": self.battery_pct,
            "updated_at": self.updated_at,
            "source": self.source,
        }


def _validate_alias(alias: str) -> str:
    value = alias.strip()
    if not value or len(value) > _MAX_ALIAS_LENGTH:
        raise ValueError(f"alias must contain 1-{_MAX_ALIAS_LENGTH} characters")
    if any(ord(ch) < 32 for ch in value):
        raise ValueError("alias contains control characters")
    return value


def validate_shared_link(url: str) -> str:
    """Accept only HTTPS Life360 sharing pages and never accept URL credentials."""
    if not isinstance(url, str):
        raise TypeError("Life360 shared link must be a string")
    value = url.strip()
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https":
        raise ValueError("Life360 shared link must use HTTPS")
    if not host or not (host == "life360.com" or host.endswith(_LIFE360_HOST_SUFFIX)):
        raise ValueError("Life360 shared link must use a Life360 domain")
    if parsed.username or parsed.password:
        raise ValueError("credentials are not permitted in a Life360 shared link")
    if not parsed.path or parsed.path == "/":
        raise ValueError("Life360 shared link path is required")
    return value


def _find_first(mapping: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _coerce_coordinate(value: object, name: str, lower: float, upper: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Life360 {name} is invalid") from exc
    if not lower <= result <= upper:
        raise ValueError(f"Life360 {name} must be between {lower} and {upper}")
    return result


def _coerce_accuracy(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _coerce_battery(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= raw <= 1.0:
        raw *= 100.0
    return int(round(min(max(raw, 0.0), 100.0)))


def parse_shared_location_payload(payload: dict, *, alias: str) -> Life360Location:
    """Normalize a browser-visible JSON object without retaining unrelated fields."""
    if not isinstance(payload, dict):
        raise TypeError("Life360 payload must be an object")
    safe_alias = _validate_alias(alias)

    selected = None
    for candidate in _walk_dicts(payload):
        latitude = _find_first(candidate, ("latitude", "lat"))
        longitude = _find_first(candidate, ("longitude", "lon", "lng"))
        if latitude is not None and longitude is not None:
            selected = candidate
            break
    if selected is None:
        raise ValueError("Life360 shared location payload did not contain coordinates")

    member = next((item for item in _walk_dicts(payload) if _find_first(item, ("name", "displayName", "memberName"))), {})
    latitude = _coerce_coordinate(_find_first(selected, ("latitude", "lat")), "latitude", -90.0, 90.0)
    longitude = _coerce_coordinate(_find_first(selected, ("longitude", "lon", "lng")), "longitude", -180.0, 180.0)

    return Life360Location(
        alias=safe_alias,
        latitude=latitude,
        longitude=longitude,
        name=str(_find_first(member, ("name", "displayName", "memberName")) or "").strip() or None,
        accuracy_m=_coerce_accuracy(_find_first(selected, ("accuracy", "accuracy_m", "accuracyMeters"))),
        battery_pct=_coerce_battery(
            _find_first(selected, ("battery", "batteryLevel", "battery_pct", "batteryPercent"))
        ),
        updated_at=str(
            _find_first(selected, ("updatedAt", "updated_at", "timestamp", "lastUpdated")) or ""
        ).strip()
        or None,
    )


def _extract_json_scripts(html: str) -> list[dict]:
    result: list[dict] = []
    for block in re.findall(
        r"<script[^>]*type=[\"']application/(?:ld\+json|json)[\"'][^>]*>(.*?)</script>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        try:
            parsed = json.loads(block.strip())
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            result.append(parsed)
        elif isinstance(parsed, list):
            result.extend(item for item in parsed if isinstance(item, dict))
    return result


def extract_location_from_html(html: str, *, alias: str) -> Life360Location:
    """Extract coordinates only from rendered/embedded page data; never calls Life360 APIs."""
    if not isinstance(html, str) or not html.strip():
        raise ValueError("Life360 page content is empty")

    for element in re.finditer(r"<[^>]+>", html, flags=re.DOTALL):
        tag = element.group(0)
        lat = re.search(r"(?:data-)?latitude\s*=\s*[\"'](-?\d+(?:\.\d+)?)[\"']", tag, re.I)
        lon = re.search(r"(?:data-)?longitude\s*=\s*[\"'](-?\d+(?:\.\d+)?)[\"']", tag, re.I)
        if lat and lon:
            payload = {
                "latitude": lat.group(1),
                "longitude": lon.group(1),
                "battery": (re.search(r"(?:data-)?battery(?:-percent)?\s*=\s*[\"']([^\"']+)", tag, re.I) or [None, None])[1],
                "updatedAt": (re.search(r"(?:data-)?(?:updated-at|last-updated)\s*=\s*[\"']([^\"']+)", tag, re.I) or [None, None])[1],
            }
            return parse_shared_location_payload(payload, alias=alias)

    for payload in _extract_json_scripts(html):
        try:
            return parse_shared_location_payload(payload, alias=alias)
        except ValueError:
            continue

    raise ValueError("Life360 page did not expose a supported shared location")


class Life360SharedLinkReader:
    """Read an already-authorized Life360 shared page with Jarvis's browser session."""

    def __init__(self, browser=None, timeout_ms: int = 20_000):
        self._browser = browser
        self._timeout_ms = max(1_000, min(timeout_ms, 60_000))

    def read(self, share_url: str, *, alias: str) -> Life360Location:
        safe_url = validate_shared_link(share_url)
        if self._browser is None:
            from browser.browser import get_browser

            self._browser = get_browser()
        page = self._browser.get_page()
        page.goto(safe_url, wait_until="domcontentloaded", timeout=self._timeout_ms)
        return extract_location_from_html(page.content(), alias=alias)
