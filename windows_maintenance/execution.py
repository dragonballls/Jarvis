from __future__ import annotations

from .audit import append_record, new_record
from .errors import VerificationFailed
from .models import MaintenanceAction, OperationResult
from .policy import MaintenancePolicy
from .validator import validate_action


class MaintenanceExecutor:
    """Enforces policy -> execute -> verify -> rollback when supplied."""

    def __init__(self, policy: MaintenancePolicy | None = None):
        self.policy = policy or MaintenancePolicy()

    def execute(self, action: MaintenanceAction, adapter, *, explicit_user_request: bool = False, rollback=None) -> OperationResult:
        validate_action(action)
        decision = self.policy.evaluate(action, explicit_user_request=explicit_user_request)
        if not decision.allowed:
            return OperationResult(action.operation, action.target_id, False, error=decision.reason)
        try:
            result = adapter(action)
            if not result.verified:
                raise VerificationFailed(result.error or "mutation verification failed")
        except Exception as exc:
            rollback_attempted = False
            if rollback is not None:
                rollback_attempted = True
                try:
                    rollback(action)
                except Exception:
                    pass
            failed = OperationResult(action.operation, action.target_id, False, rollback_attempted=rollback_attempted, error=str(exc))
            append_record(new_record(action.operation, action.target_id, verified=False, rollback={"attempted": rollback_attempted}))
            return failed
        append_record(new_record(action.operation, action.target_id, resulting_state={"changed": result.changed}, verified=result.verified))
        return result
