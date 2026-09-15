from .adapters import process_list, stop_process
from .models import MaintenanceAction, OperationResult, RiskClass
from .policy import MaintenancePolicy
from .validator import validate_action


class ProcessManager:
    def __init__(self, policy: MaintenancePolicy | None = None):
        self.policy = policy or MaintenancePolicy()

    def candidates(self, protected_pids: set[int] | None = None) -> list[dict]:
        protected = protected_pids or set()
        rows = []
        for item in process_list():
            try:
                pid = int(item.get("Id"))
            except (TypeError, ValueError):
                continue
            if pid not in protected and item.get("Path"):
                rows.append(item)
        return rows

    def stop(self, name: str, pid: int, explicit_user_request: bool = True) -> OperationResult:
        action = validate_action(MaintenanceAction("process.stop", name, {"pid": int(pid)}, RiskClass.REVERSIBLE_LOW_RISK))
        decision = self.policy.evaluate(action, explicit_user_request=explicit_user_request)
        if not decision.allowed:
            return OperationResult(action.operation, action.target_id, False, error=decision.reason)
        try:
            ok, detail = stop_process(pid, name.removesuffix(".exe"))
            return OperationResult(action.operation, action.target_id, ok, changed=ok, verified=ok, detail=detail)
        except Exception as exc:
            return OperationResult(action.operation, action.target_id, False, error=str(exc))
