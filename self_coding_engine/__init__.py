"""Portable autonomous self-coding engine.

This package intentionally has no dependency on Jarvis, Friday, desktop UI,
application-specific providers, or application registries. A host supplies
four callbacks: plan, execute, verify, and optional repair.
"""

from .engine import (
    CodingAttempt,
    CodingEngineError,
    CodingEvent,
    CodingPlan,
    CodingStep,
    SelfCodingEngine,
)

__all__ = [
    "CodingAttempt",
    "CodingEngineError",
    "CodingEvent",
    "CodingPlan",
    "CodingStep",
    "SelfCodingEngine",
]
