"""Isolated Jarvis self-coding boundary.

Self-coding owns only the Jarvis self-coding workspace and delegates execution
to the existing OpenHands/OpenCode integration. It does not own Jarvis's
packaged updater and does not manage Mark 53.
"""

from .engine import SelfCodingConfig, SelfCodingEngine

__all__ = ["SelfCodingConfig", "SelfCodingEngine"]
