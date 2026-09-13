from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class OpenHandsUnavailable(RuntimeError):
    """Raised when the optional OpenHands SDK cannot initialize."""


def _load_openhands() -> tuple[Any, Any, Any, Any, Any]:
    try:
        from openhands.sdk import Agent, Conversation, LLM, Tool
        from openhands.tools.file_editor import FileEditorTool
        from openhands.tools.task_tracker import TaskTrackerTool
        from openhands.tools.terminal import TerminalTool
    except Exception as exc:  # pragma: no cover - runtime-dependent import
        raise OpenHandsUnavailable(str(exc)) from exc
    return Agent, Conversation, LLM, Tool, (FileEditorTool, TaskTrackerTool, TerminalTool)


def openhands_available() -> bool:
    try:
        _load_openhands()
    except OpenHandsUnavailable:
        return False
    return True


def _model_name() -> str:
    return (
        os.getenv("JARVIS_OPENHANDS_MODEL")
        or os.getenv("OPENHANDS_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "gpt-5.5"
    )


def _api_key() -> str:
    value = os.getenv("JARVIS_OPENHANDS_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not value:
        raise OpenHandsUnavailable("No remote LLM API key is configured for OpenHands.")
    return value


def run_once(workspace: Path, goal: str) -> list[dict[str, Any]]:
    """Run one bounded OpenHands coding conversation.

    The SDK is optional and loaded lazily. Jarvis does not select a local model.
    This wrapper converts the SDK's non-streaming conversation lifecycle into the
    small event shape already used by Jarvis's coding API.
    """
    Agent, Conversation, LLM, Tool, tools = _load_openhands()
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise OpenHandsUnavailable(f"Workspace does not exist: {workspace}")

    from pydantic import SecretStr

    llm = LLM(model=_model_name(), api_key=SecretStr(_api_key()))
    agent = Agent(
        llm=llm,
        tools=[Tool(name=tool.name) for tool in tools],
    )
    conversation = Conversation(
        agent=agent,
        workspace=workspace,
        max_iteration_per_run=int(os.getenv("JARVIS_OPENHANDS_MAX_ITERATIONS", "50")),
        delete_on_close=False,
    )
    conversation.send_message(goal)
    conversation.run()

    return [
        {"type": "agent_event", "event": "openhands_completed", "workspace": str(workspace)},
        {"type": "done", "content": "OpenHands coding run completed successfully.", "final": True},
    ]
