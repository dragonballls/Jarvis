from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class OpenHandsUnavailable(RuntimeError):
    """Raised when the optional OpenHands SDK is not installed or cannot initialize."""


def _load_openhands() -> tuple[Any, Any, Any, Any, Any]:
    try:
        from openhands.sdk import Agent, Conversation, LLM, Tool
        from openhands.tools.file_editor import FileEditorTool
        from openhands.tools.task_tracker import TaskTrackerTool
        from openhands.tools.terminal import TerminalTool
    except Exception as exc:  # pragma: no cover - depends on optional runtime
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
    """Run a bounded OpenHands coding session and return normalized Jarvis events.

    OpenHands is intentionally loaded lazily so Jarvis still boots when the optional
    SDK is not installed. No local model is selected here; the model and credential
    are supplied by the environment.
    """
    Agent, Conversation, LLM, Tool, tools = _load_openhands()
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise OpenHandsUnavailable(f"Workspace does not exist: {workspace}")

    llm = LLM(model=_model_name(), api_key=_api_key())
    agent = Agent(
        llm=llm,
        tools=[Tool(name=tool.name) for tool in tools],
    )
    conversation = Conversation(agent=agent, workspace=str(workspace))

    events: list[dict[str, Any]] = []
    conversation.send_message(goal)
    for event in conversation.run():
        event_type = getattr(event, "type", None) or event.__class__.__name__
        payload: dict[str, Any] = {"type": "agent_event", "event": str(event_type)}
        content = getattr(event, "content", None)
        if content:
            payload["content"] = str(content)
        events.append(payload)
    events.append({"type": "done", "content": "OpenHands run completed.", "final": True})
    return events
