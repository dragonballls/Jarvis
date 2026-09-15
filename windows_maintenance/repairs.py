from __future__ import annotations

from .adapters import network_reset, repair_system_files
from .models import MaintenanceAction, OperationResult, RiskClass
from .policy import MaintenancePolicy


class RepairManager:
    """Small allowlisted set of Windows repairs; callers still need policy checks."""

    def __init__(self, policy: MaintenancePolicy | None = None):
        self.policy = policy or MaintenancePolicy()

    def scan_system_files(self) -> OperationResult:
        action = MaintenanceAction("system.files.restore", "Windows system files", {}, RiskClass.HIGH_RISK)
        decision = self.policy.evaluate(action, explicit_user_request=False)
        if decision.allowed:
            ok, detail = repair_system_files(scan_only=True)
            return OperationResult(action.operation, action.target_id, ok, changed=False, verified=ok, detail=detail)
        return OperationResult(action.operation, action.target_id, False, error="Diagnostic scan is read-only; repair requires explicit high-risk confirmation.")

    def repair_system_files(self, confirmed: bool = False) -> OperationResult:
        action = MaintenanceAction("system.files.restore", "Windows system files", {}, RiskClass.HIGH_RISK)
        if not confirmed:
            return OperationResult(action.operation, action.target_id, False, error="Confirmation required for Windows system-file repair.")
        # Explicit confirmation is still passed through the policy boundary. The
        # default policy intentionally refuses high-risk automation; this method
        # is the future interactive confirmation seam rather than a shell escape.
        return OperationResult(action.operation, action.target_id, False, error="High-risk system repair requires the interactive confirmation registry.")

    def reset_network(self, confirmed: bool = False) -> OperationResult:
        action = MaintenanceAction("network.reset", "Windows network configuration", {}, RiskClass.HIGH_RISK)
        if not confirmed:
            return OperationResult(action.operation, action.target_id, False, error="Confirmation required for network reset.")
        return OperationResult(action.operation, action.target_id, False, error="High-risk network reset requires the interactive confirmation registry.")
