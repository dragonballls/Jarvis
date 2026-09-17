from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GUI_SMOKE = REPO_ROOT / "packaging" / "windows" / "gui_smoke_test.ps1"


def test_gui_smoke_does_not_activate_non_gui_smoke_mode():
    script = GUI_SMOKE.read_text(encoding="utf-8")
    assert "$env:JARVIS_SMOKE_TEST" not in script
