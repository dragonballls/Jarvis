from __future__ import annotations

from collections.abc import Callable

from .adapters import diagnostics as windows_diagnostics
from .models import DiagnosticFinding, DiagnosticReport


class DiagnosticCollector:
    def __init__(self, checks: list[Callable] | None = None):
        self.checks = checks or [windows_diagnostics]

    def collect(self) -> DiagnosticReport:
        findings: list[DiagnosticFinding] = []
        failures: list[str] = []
        for check in self.checks:
            try:
                raw = check()
                if not isinstance(raw, dict):
                    continue
                for category, value in raw.items():
                    if isinstance(value, dict) and value.get("error"):
                        failures.append(f"{category}: {value['error']}")
                        continue
                    if category == "memory" and isinstance(value, dict):
                        total = float(value.get("TotalVisibleMemorySize") or 0)
                        free = float(value.get("FreePhysicalMemory") or 0)
                        used = ((total - free) / total * 100) if total else 0
                        if used >= 90:
                            findings.append(
                                DiagnosticFinding(
                                    "memory",
                                    "warning",
                                    "High memory pressure",
                                    f"Memory usage is about {used:.0f}%.",
                                    data=value,
                                )
                            )
                    elif category == "cpu" and isinstance(value, list):
                        high = [x for x in value if float(x.get("LoadPercentage") or 0) >= 90]
                        if high:
                            findings.append(
                                DiagnosticFinding(
                                    "cpu",
                                    "warning",
                                    "High CPU pressure",
                                    "One or more CPUs report sustained high load.",
                                    data={"processors": high},
                                )
                            )
                    elif category == "disks":
                        items = value if isinstance(value, list) else [value]
                        for disk in items:
                            size = float(disk.get("Size") or 0)
                            free = float(disk.get("FreeSpace") or 0)
                            if size and free / size < 0.10:
                                findings.append(
                                    DiagnosticFinding(
                                        "disk",
                                        "warning",
                                        f"Low free space on {disk.get('DeviceID')}",
                                        "Less than 10% free space reported.",
                                        data=disk,
                                    )
                                )
                    elif category == "devices" and value:
                        items = value if isinstance(value, list) else [value]
                        findings.append(
                            DiagnosticFinding(
                                "devices",
                                "warning",
                                "Device problems detected",
                                f"{len(items)} device(s) report a non-OK status.",
                                data={"devices": items},
                            )
                        )
                    elif category == "errors" and value:
                        items = value if isinstance(value, list) else [value]
                        findings.append(
                            DiagnosticFinding(
                                "errors",
                                "warning",
                                "Recent Windows errors detected",
                                f"{len(items)} system error event(s) were found in the lookback window.",
                                data={"events": items},
                            )
                        )
            except Exception as exc:
                failures.append(f"{getattr(check, '__name__', 'diagnostic')}: {exc}")
        return DiagnosticReport(tuple(findings), tuple(failures))
