from __future__ import annotations

from typing import Protocol

from .models import DiagnosticReport, MaintenanceAction, OperationResult


class DiagnosticAdapter(Protocol):
    def __call__(self) -> dict: ...


class MutationAdapter(Protocol):
    def execute(self, action: MaintenanceAction) -> OperationResult: ...


class VerificationAdapter(Protocol):
    def verify(self, action: MaintenanceAction, result: OperationResult) -> bool: ...


class AuditSink(Protocol):
    def append(self, record: dict) -> None: ...


__all__ = ["DiagnosticAdapter", "MutationAdapter", "VerificationAdapter", "AuditSink", "DiagnosticReport"]
