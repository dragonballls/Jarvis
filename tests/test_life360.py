from __future__ import annotations

import pytest

from integrations.life360.shared_link import (
    Life360Location,
    extract_location_from_html,
    parse_shared_location_payload,
    validate_shared_link,
)
from integrations.life360.service import Life360Service


def test_validate_shared_link_accepts_https_life360_only() -> None:
    assert validate_shared_link("https://share.life360.com/share/abc") == "https://share.life360.com/share/abc"
    with pytest.raises(ValueError):
        validate_shared_link("http://share.life360.com/share/abc")
    with pytest.raises(ValueError):
        validate_shared_link("https://example.com/share/abc")
    with pytest.raises(ValueError):
        validate_shared_link("https://user:pass@share.life360.com/share/abc")


def test_parse_shared_location_payload_normalizes_fields() -> None:
    location = parse_shared_location_payload(
        {
            "member": {"name": "Alex", "battery": 0.76},
            "location": {
                "latitude": 34.123456,
                "longitude": -117.987654,
                "accuracy": 12.5,
                "updatedAt": "2026-09-17T00:00:00Z",
            },
        },
        alias="family_alex",
    )
    assert isinstance(location, Life360Location)
    assert location.alias == "family_alex"
    assert location.name == "Alex"
    assert location.latitude == 34.123456
    assert location.longitude == -117.987654
    assert location.accuracy_m == 12.5
    assert location.battery_pct == 76
    assert location.updated_at == "2026-09-17T00:00:00Z"


def test_extract_location_from_rendered_page_data() -> None:
    html = '''
    <div data-latitude="34.050000" data-longitude="-118.250000"
         data-battery="81" data-updated-at="2026-09-17T00:01:02Z"></div>
    '''
    location = extract_location_from_html(html, alias="mom")
    assert location.latitude == 34.05
    assert location.longitude == -118.25
    assert location.battery_pct == 81
    assert location.updated_at == "2026-09-17T00:01:02Z"


def test_parse_rejects_payload_without_coordinates() -> None:
    with pytest.raises(ValueError, match="coordinates"):
        parse_shared_location_payload({"member": {"name": "Alex"}}, alias="alex")


def test_service_status_never_returns_share_links() -> None:
    service = Life360Service()
    service.add_shared_link("alex", "https://share.life360.com/share/opaque-token")
    status = service.status()
    assert status["members"] == [{"alias": "alex", "has_shared_link": True, "has_location": False}]
    assert "opaque-token" not in str(status)
