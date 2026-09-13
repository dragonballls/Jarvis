from pathlib import Path
import sys

from self_coding_engine import CodingPlan, CodingStep, SelfCodingEngine


def test_engine_can_write_and_verify_without_application_imports(tmp_path: Path):
    target = tmp_path / "example.txt"

    def planner(goal, context):
        return CodingPlan(goal, (CodingStep("write", "write example", ("example.txt",)),))

    def executor(step, workspace, context):
        (workspace / "example.txt").write_text("detached", encoding="utf-8")
        return {"success": True}

    def verifier(step, workspace):
        return (workspace / "example.txt").read_text(encoding="utf-8") == "detached"

    engine = SelfCodingEngine(planner=planner, executor=executor, verifier=verifier)
    events = list(engine.run("create example", workspace=tmp_path))

    assert target.read_text(encoding="utf-8") == "detached"
    assert events[-1].type == "completed"


def test_path_escape_is_rejected(tmp_path: Path):
    def planner(goal, context):
        return CodingPlan(goal, (CodingStep("bad", "bad", ("../escape.txt",)),))

    engine = SelfCodingEngine(
        planner=planner,
        executor=lambda step, workspace, context: None,
        verifier=lambda step, workspace: True,
    )

    try:
        list(engine.run("bad", workspace=tmp_path))
    except Exception as exc:
        assert "escapes workspace" in str(exc)
    else:
        raise AssertionError("workspace escape was accepted")


def test_module_does_not_import_jarvis_or_friday_names():
    source = Path("self_coding_engine/engine.py").read_text(encoding="utf-8").lower()
    assert "from agent" not in source
    assert "from core" not in source
    assert "from desktop" not in source
    assert "friday" not in source
    assert "jarvis" not in source
