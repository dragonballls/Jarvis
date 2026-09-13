from __future__ import annotations

from pathlib import Path

from mark53.bridge import Mark53Bridge, Mark53Config, mark53_enabled
from mark_updater import MARK_COMPONENT, UPDATER_COMPONENT
from self_coding.engine import SelfCodingConfig, SelfCodingEngine


def test_mark53_bridge_requires_explicit_external_endpoint(monkeypatch):
    monkeypatch.delenv("JARVIS_MARK53_URL", raising=False)
    assert Mark53Config.from_environment() is None
    assert not mark53_enabled()


def test_mark53_bridge_rejects_non_http_urls():
    try:
        Mark53Bridge(Mark53Config("file:///unsafe"))
    except ValueError:
        pass
    else:
        raise AssertionError("Mark 53 bridge accepted a non-HTTP endpoint")


def test_mark_updater_has_distinct_identity():
    assert MARK_COMPONENT == "mark53"
    assert UPDATER_COMPONENT == "mark_updater"
    assert MARK_COMPONENT != UPDATER_COMPONENT


def test_self_coding_rejects_missing_workspace(tmp_path: Path):
    missing = tmp_path / "missing"
    try:
        SelfCodingEngine(SelfCodingConfig(missing))
    except ValueError:
        pass
    else:
        raise AssertionError("Self-coding accepted a missing workspace")


def test_self_coding_empty_goal_is_safe(tmp_path: Path):
    engine = SelfCodingEngine(SelfCodingConfig(tmp_path))
    events = list(engine.run("   "))
    assert events == [{"type": "error", "error": "Self-coding goal is empty.", "final": True}]
