"""Isolated Mark updater boundary.

This package is intentionally independent from Jarvis self-coding and from
the Windows Jarvis updater. It exists so Mark 53 can have its own release and
update lifecycle without sharing mutable files with Jarvis.
"""

MARK_COMPONENT = "mark53"
UPDATER_COMPONENT = "mark_updater"

__all__ = ["MARK_COMPONENT", "UPDATER_COMPONENT"]
