from .models import MaintenanceAction, PolicyDecision, RiskClass

PROTECTED_NAMES = {
    "jarvis.exe", "omniroute.exe", "system", "system idle process", "smss.exe",
    "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "winlogon.exe",
    "svchost.exe", "dwm.exe", "explorer.exe", "securityhealthservice.exe",
    "msmpeng.exe", "antimalware service executable",
}

ALLOWED_MUTATIONS = {
    "process.stop": RiskClass.REVERSIBLE_LOW_RISK,
    "startup.disable": RiskClass.REVERSIBLE_MEDIUM_RISK,
    "startup.enable": RiskClass.REVERSIBLE_MEDIUM_RISK,
    "system.files.restore": RiskClass.HIGH_RISK,
    "network.reset": RiskClass.HIGH_RISK,
    "application.repair": RiskClass.REVERSIBLE_MEDIUM_RISK,
}


class MaintenancePolicy:
    def __init__(self, extra_protected: set[str] | None = None):
        self.protected = set(PROTECTED_NAMES)
        self.protected.update(x.lower() for x in (extra_protected or set()))

    def evaluate(self, action: MaintenanceAction, explicit_user_request: bool = False, persistent_authorized: bool = False) -> PolicyDecision:
        if action.risk == RiskClass.READ_ONLY:
            return PolicyDecision(True, "read-only operation")
        required = ALLOWED_MUTATIONS.get(action.operation)
        if required is None:
            return PolicyDecision(False, f"unsupported operation: {action.operation}")
        if action.risk != required:
            return PolicyDecision(False, "action risk does not match supported operation")
        target = action.target_id.lower().strip()
        if target in self.protected or any(target.endswith("\\" + name) for name in self.protected):
            return PolicyDecision(False, f"protected target: {action.target_id}")
        if action.operation == "process.stop" and not explicit_user_request:
            return PolicyDecision(False, "process cleanup requires explicit user intent")
        if action.operation.startswith("startup.") and not (explicit_user_request or persistent_authorized):
            return PolicyDecision(False, "startup changes require explicit authorization")
        if action.risk == RiskClass.HIGH_RISK:
            return PolicyDecision(False, "high-risk repair is not automatic", requires_confirmation=True)
        return PolicyDecision(True, "policy allows supported action", requires_confirmation=False)
