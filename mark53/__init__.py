"""Isolated Mark 53 integration boundary.

Mark 53 is intentionally a separate component. Jarvis may communicate with
it through the bridge, but Jarvis self-coding and updater code must never edit
Mark 53 files or binaries.
"""

from .bridge import Mark53Bridge, Mark53Config

__all__ = ["Mark53Bridge", "Mark53Config"]
