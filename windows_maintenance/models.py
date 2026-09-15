from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE_LOW_RISK = "REVERSIBLE_LOW_RISK"
    REVERSIBLE_MEDIUM_RISK = "REVERSIBLE_MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"


@dataclass(frozen=True)
class MaintenanceAction:
    operation: str
    target_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    risk: RiskClass = RiskClass.READ_ONLY
    reason: str = ""
    requires_confirmation: bool = False

    def __post_init__(self):
        if not self.operation.strip():
            raise ValueError("operation cannot be empty")
        if self.risk != RiskClass.READ_ONLY and not self.target_id.strip():
            raise ValueError("mutating actions require a target identity")


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    requires_confirmation: bool = False


@dataclass(frozen=True)
class DiagnosticFinding:
    category: str
    severity: str
    title: str
    detail: str
    confidence: str = "observed"
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperationResult:
    operation: str
    target_id: str
    success: bool
    changed: bool = False
    verified: bool = False
    rollback_available: bool = False
    rollback_attempted: bool = False
    error: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class MaintenanceRecord:
    correlation_id: str
    timestamp: str
    operation: str
    target_id: str
    previous_state: dict[str, Any] = field(default_factory=dict)
    resulting_state: dict[str, Any] = field(default_factory=dict)
    verified: bool = False
    rollback: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MaintenancePlan:
    intent: str
    actions: tuple[MaintenanceAction, ...] = ()
    explanations: tuple[str, ...] = ()
    skipped_risks: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticReport:
    findings: tuple[DiagnosticFinding, ...] = ()
    failures: tuple[str, ...] = ()
    completed_checks: int = 0

    def summary(self) -> str:
        if not self.findings and not self.failures:
            return f"Completed {self.completed_checks} Windows health checks with no findings."
        return f"Collected {len(self.findings)} findings across {self.completed_checks} completed Windows health checks."
