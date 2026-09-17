from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GUI_SMOKE = REPO_ROOT / "packaging" / "windows" / "gui_smoke_test.ps1"
WINDOWS_APP = REPO_ROOT / "packaging" / "windows" / "app.py"


def test_gui_smoke_does_not_activate_non_gui_smoke_mode():
    script = GUI_SMOKE.read_text(encoding="utf-8")
    assert "$env:JARVIS_SMOKE_TEST" not in script
    assert "$env:JARVIS_GUI_SMOKE_TEST" in script


def test_packaged_app_has_distinct_gui_smoke_mode():
    source = WINDOWS_APP.read_text(encoding="utf-8")
    assert "JARVIS_GUI_SMOKE_TEST" in source
    assert "if os.environ.get(\"JARVIS_GUI_SMOKE_TEST\") == \"1\"" in source
