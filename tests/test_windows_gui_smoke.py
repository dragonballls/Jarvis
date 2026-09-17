from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GUI_SMOKE = REPO_ROOT / "packaging" / "windows" / "gui_smoke_test.ps1"
GUI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "windows-gui.yml"


def test_gui_smoke_does_not_activate_non_gui_smoke_mode():
    script = GUI_SMOKE.read_text(encoding="utf-8")
    assert "$env:JARVIS_SMOKE_TEST" not in script


def test_hosted_gui_gate_detects_missing_interactive_desktop():
    script = GUI_SMOKE.read_text(encoding="utf-8")
    assert "SessionId" in script
    assert "explorer" in script
    assert "interactive desktop" in script.lower()


def test_interactive_gui_workflow_exists():
    workflow = GUI_WORKFLOW.read_text(encoding="utf-8")
    assert "self-hosted" in workflow
    assert "windows" in workflow
    assert "gui" in workflow
    assert "gui_smoke_test.ps1" in workflow
