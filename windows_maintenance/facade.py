from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import DiagnosticCollector
from .models import DiagnosticReport, MaintenanceAction, MaintenancePlan, OperationResult, RiskClass
from .policy import MaintenancePolicy
from .processes import ProcessManager
from .startup import StartupManager


@dataclass(frozen=True)
class MaintenanceResponse:
    intent: str
    report: DiagnosticReport | None = None
    plan: MaintenancePlan | None = None
    results: tuple[OperationResult, ...] = ()
    message: str = ""


def is_maintenance_request(text: str) -> bool:
    value = text.lower()
    markers = (
        "diagnose my pc", "diagnose my computer", "fix my pc", "fix my computer",
        "repair my pc", "repair my computer", "optimize my pc", "optimize my computer",
        "clean up whatever", "clean up my pc", "stop steam", "startup", "running in the background",
        "wasting resources", "system files", "windows errors", "network problems",
    )
    return any(marker in value for marker in markers)


class MaintenanceFacade:
    def __init__(self, policy: MaintenancePolicy | None = None):
        self.policy = policy or MaintenancePolicy()
        self.diagnostics = DiagnosticCollector()
        self.processes = ProcessManager(self.policy)
        self.startup = StartupManager(self.policy)

    def diagnose(self) -> MaintenanceResponse:
        report = self.diagnostics.collect()
        return MaintenanceResponse("diagnose", report=report, message=self._report_message(report))

    def handle(self, request: str) -> MaintenanceResponse:
        lowered = request.lower()
        if "diagnos" in lowered and not ("fix" in lowered or "repair" in lowered or "clean" in lowered):
            return self.diagnose()
        report = self.diagnostics.collect()
        actions: list[MaintenanceAction] = []
        skipped: list[str] = []
        if "steam" in lowered and ("stop" in lowered or "background" in lowered):
            for process in self.processes.candidates():
                name = str(process.get("ProcessName", ""))
                if name.lower() == "steam":
                    actions.append(MaintenanceAction("process.stop", "steam.exe", {"pid": int(process["Id"])}, RiskClass.REVERSIBLE_LOW_RISK, "User explicitly requested Steam cleanup."))
        if "startup" in lowered and ("steam" in lowered or "launch" in lowered or "start" in lowered):
            actions.append(MaintenanceAction("startup.disable", "Steam", {"name": "Steam", "source": "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"}, RiskClass.REVERSIBLE_MEDIUM_RISK, "User explicitly requested startup prevention."))
        if "network" in lowered and ("fix" in lowered or "repair" in lowered):
            skipped.append("Network reset is high-risk and requires an explicit confirmation path.")
        if "fix" in lowered or "repair" in lowered:
            skipped.append("Protected system repair is available only through the high-risk confirmation path.")
        plan = MaintenancePlan(request, tuple(actions), (report.summary(),), tuple(skipped))
        results: list[OperationResult] = []
        for action in actions:
            decision = self.policy.evaluate(action, explicit_user_request=True)
            if not decision.allowed:
                results.append(OperationResult(action.operation, action.target_id, False, error=decision.reason))
                continue
            if action.operation == "process.stop":
                pid = int(action.arguments["pid"])
                results.append(self.processes.stop(action.target_id, pid, explicit_user_request=True))
            elif action.operation == "startup.disable":
                results.append(self.startup.disable(action.arguments["name"], action.arguments["source"], authorized=True))
        return MaintenanceResponse(request, report, plan, tuple(results), self._result_message(report, plan, results))

    @staticmethod
    def _report_message(report: DiagnosticReport) -> str:
        parts = [report.summary()]
        for finding in report.findings[:8]:
            parts.append(f"{finding.severity}: {finding.title} — {finding.detail}")
        if report.failures:
            parts.append(f"{len(report.failures)} diagnostic checks failed without aborting the remaining checks.")
        return "\n".join(parts)

    @classmethod
    def _result_message(cls, report: DiagnosticReport, plan: MaintenancePlan, results: list[OperationResult]) -> str:
        lines = [cls._report_message(report)]
        for result in results:
            status = "verified" if result.success and result.verified else "failed"
            lines.append(f"{result.operation} on {result.target_id}: {status}. {result.detail or result.error or ''}".strip())
        lines.extend(f"Not performed: {item}" for item in plan.skipped_risks)
        return "\n".join(lines)
