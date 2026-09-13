from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SelfCodingConfig:
    """Explicit boundary for Jarvis self-coding configuration."""

    workspace: Path
    engine: str = "auto"


class SelfCodingEngine:
    """Facade for Jarvis self-coding only.

    OpenHands/OpenCode remain the execution engines. This facade owns no Mark
    53 state and performs no Jarvis executable replacement; executable updates
    belong exclusively to the Windows updater.
    """

    def __init__(self, config: SelfCodingConfig) -> None:
        workspace = config.workspace.resolve()
        if not workspace.is_dir():
            raise ValueError(f"Self-coding workspace does not exist: {workspace}")
        self.config = SelfCodingConfig(workspace=workspace, engine=config.engine)

    def run(self, goal: str) -> Generator[dict, None, None]:
        if not goal.strip():
            yield {"type": "error", "error": "Self-coding goal is empty.", "final": True}
            return
        from core.opencode_agent import run_coding_agent

        for event in run_coding_agent(self.config.workspace, goal):
            yield event
