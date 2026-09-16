from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any


def _ps(script: str, timeout: int = 20) -> Any:
    if os.name != "nt":
        raise RuntimeError("Windows-only operation")
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"PowerShell exited {completed.returncode}")
    text = completed.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def diagnostics() -> dict[str, Any]:
    if os.name != "nt":
        return {"platform": sys.platform, "windows": False}
    result: dict[str, Any] = {"platform": "windows", "windows": True}
    checks = {
        "os": "Get-CimInstance Win32_OperatingSystem | Select Caption,Version,LastBootUpTime | ConvertTo-Json -Compress",
        "cpu": "Get-CimInstance Win32_Processor | Select Name,NumberOfLogicalProcessors,LoadPercentage | ConvertTo-Json -Compress",
        "memory": "Get-CimInstance Win32_OperatingSystem | Select TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Compress",
        "disks": "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select DeviceID,FreeSpace,Size,HealthStatus | ConvertTo-Json -Compress",
        "gpu": "Get-CimInstance Win32_VideoController | Select Name,DriverVersion,AdapterRAM | ConvertTo-Json -Compress",
        "startup": "Get-CimInstance Win32_StartupCommand | Select Name,Command,Location,User | ConvertTo-Json -Compress",
        "services": "Get-CimInstance Win32_Service | Where State -eq 'Running' | Measure-Object | Select Count | ConvertTo-Json -Compress",
        "network": "Get-NetIPConfiguration | Select InterfaceAlias,IPv4Address,IPv6Address,DNSServer,NetProfile.Name | ConvertTo-Json -Compress",
        "updates": "Get-Service wuauserv,bits -ErrorAction SilentlyContinue | Select Name,Status,StartType | ConvertTo-Json -Compress",
        "devices": "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where Status -ne 'OK' | Select FriendlyName,Class,Status,ProblemCode | ConvertTo-Json -Compress",
        "errors": "Get-WinEvent -FilterHashtable @{LogName='System';Level=2;StartTime=(Get-Date).AddDays(-3)} -MaxEvents 20 -ErrorAction SilentlyContinue | Select TimeCreated,ProviderName,Id,Message | ConvertTo-Json -Compress",
    }
    for name, script in checks.items():
        try:
            result[name] = _ps(script)
        except Exception as exc:
            result[name] = {"error": str(exc)}
    return result


def process_list() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    script = "Get-Process | Select Id,ProcessName,Path,CPU,Responding | ConvertTo-Json -Compress"
    data = _ps(script)
    if data is None:
        return []
    return data if isinstance(data, list) else [data]


def stop_process(pid: int, expected_name: str) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Windows-only operation"
    data = _ps(f"$p=Get-Process -Id {int(pid)} -ErrorAction Stop; if($p.ProcessName -ne '{expected_name.replace(chr(39), chr(39)*2).replace(chr(92), '')}'){{throw 'process identity changed'}}; Stop-Process -Id {int(pid)} -Force -ErrorAction Stop; Start-Sleep -Milliseconds 400; [bool](Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue)")
    alive = bool(data)
    return (not alive), ("stopped and verified" if not alive else "process still exists")


def startup_entries() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    raw = _ps("Get-CimInstance Win32_StartupCommand | Select Name,Command,Location,User | ConvertTo-Json -Compress")
    if raw is None:
        return []
    return raw if isinstance(raw, list) else [raw]


def startup_disable(name: str) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Windows-only operation"
    escaped = name.replace("'", "''")
    _ps(f"$item=Get-CimInstance Win32_StartupCommand | Where-Object Name -eq '{escaped}' | Select -First 1; if(-not $item){{throw 'startup item not found'}}; Disable-ScheduledTask -TaskName $item.Name -ErrorAction SilentlyContinue | Out-Null")
    return True, "startup entry disable request applied"
