from __future__ import annotations

from datetime import datetime, timezone

from . import persistence
from .adapters import disable_run_entry, restore_run_entry, startup_entries
from .models import MaintenanceAction, OperationResult, RiskClass
from .policy import MaintenancePolicy
from .validator import validate_action

ALLOWED_RUN_SOURCE = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"


class StartupManager:
    def __init__(self, policy: MaintenancePolicy | None = None):
        self.policy = policy or MaintenancePolicy()

    def inventory(self) -> list[dict]:
        return startup_entries()

    def _find(self, name: str, source: str) -> dict | None:
        for item in self.inventory():
            if str(item.get("Name", "")).lower() == name.lower() and source.lower() in str(item.get("Location", "")).lower():
                return item
        return None

    def disable(self, name: str, source: str = ALLOWED_RUN_SOURCE, authorized: bool = True) -> OperationResult:
        action = validate_action(MaintenanceAction("startup.disable", name, {"name": name, "source": source}, RiskClass.REVERSIBLE_MEDIUM_RISK))
        decision = self.policy.evaluate(action, explicit_user_request=authorized)
        if not decision.allowed:
            return OperationResult(action.operation, action.target_id, False, error=decision.reason)
        item = self._find(name, source)
        if item is None:
            policy_key = f"{source}|{name.lower()}"
            if policy_key in persistence.load_policies():
                return OperationResult(action.operation, action.target_id, True, changed=False, verified=True, detail="startup entry already absent; persistent block retained")
            return OperationResult(action.operation, action.target_id, False, error="startup entry not found or not confidently classified")
        location = str(item.get("Location", ""))
        if source not in location and source not in str(item.get("Command", "")):
            return OperationResult(action.operation, action.target_id, False, error="startup source could not be verified")
        try:
            previous = disable_run_entry(name, source)
            key = f"{source}|{name.lower()}"
            persistence.save_policy(key, {"name": name, "source": source, "previous": previous.get("previous", ""), "desired": "disabled", "timestamp": datetime.now(timezone.utc).isoformat(), "reason": "user requested startup prevention"})
            verified = self._find(name, source) is None
            if not verified:
                restore_run_entry(name, str(previous.get("previous", "")))
                return OperationResult(action.operation, action.target_id, False, rollback_available=True, rollback_attempted=True, error="startup disable could not be verified")
            return OperationResult(action.operation, action.target_id, True, changed=True, verified=True, rollback_available=True, detail="disabled persistently in the current-user Run source")
        except Exception as exc:
            return OperationResult(action.operation, action.target_id, False, error=str(exc))

    def reconcile_policies(self) -> list[dict]:
        current = self.inventory()
        current_keys = {f"{x.get('Location')}|{str(x.get('Name', '')).lower()}" for x in current}
        return [v | {"policy_key": k, "recreated": True} for k, v in persistence.load_policies().items() if v.get("desired") == "disabled" and k in current_keys]

    def rollback(self, name: str, source: str = ALLOWED_RUN_SOURCE) -> OperationResult:
        key = f"{source}|{name.lower()}"
        record = persistence.load_policies().get(key)
        if not record:
            return OperationResult("startup.enable", name, False, error="no rollback record exists")
        try:
            restore_run_entry(name, str(record.get("previous", "")))
            persistence.remove_policy(key)
            verified = self._find(name, source) is not None
            return OperationResult("startup.enable", name, verified, changed=True, verified=verified, detail="startup entry restored" if verified else "restore not verified")
        except Exception as exc:
            return OperationResult("startup.enable", name, False, error=str(exc))
