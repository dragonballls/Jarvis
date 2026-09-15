"""Windows maintenance adapters with non-Windows-safe fallbacks for CI/imports."""

from __future__ import annotations

import platform
import subprocess
from typing import Any


def _powershell(script: str) -> str:
    if platform.system() != "Windows":
        return ""
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout or "PowerShell command failed").strip())
    return completed.stdout.strip()


def diagnostics() -> dict[str, Any]:
    if platform.system() != "Windows":
        return {"platform": {"name": platform.system(), "supported": False}}
    return {
        "platform": {"name": platform.system(), "supported": True},
        "memory": _memory(),
        "cpu": _cpu(),
        "disks": _disks(),
        "devices": _devices(),
        "errors": _recent_errors(),
    }


def _memory() -> dict[str, Any]:
    output = _powershell("Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Compress")
    return __import__("json").loads(output) if output else {}


def _cpu() -> list[dict[str, Any]]:
    output = _powershell("Get-CimInstance Win32_Processor | Select-Object Name,LoadPercentage,NumberOfLogicalProcessors | ConvertTo-Json -Compress")
    if not output:
        return []
    value = __import__("json").loads(output)
    return value if isinstance(value, list) else [value]


def _disks() -> list[dict[str, Any]]:
    output = _powershell("Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID,Size,FreeSpace | ConvertTo-Json -Compress")
    if not output:
        return []
    value = __import__("json").loads(output)
    return value if isinstance(value, list) else [value]


def _devices() -> list[dict[str, Any]]:
    output = _powershell("Get-CimInstance Win32_PnPEntity | Where-Object { $_.Status -and $_.Status -ne 'OK' } | Select-Object Name,PNPDeviceID,Status | Select-Object -First 25 | ConvertTo-Json -Compress")
    if not output:
        return []
    value = __import__("json").loads(output)
    return value if isinstance(value, list) else [value]


def _recent_errors() -> list[dict[str, Any]]:
    output = _powershell("Get-WinEvent -FilterHashtable @{LogName='System'; Level=2; StartTime=(Get-Date).AddHours(-24)} -MaxEvents 25 | Select-Object Id,ProviderName,LevelDisplayName,TimeCreated,Message | ConvertTo-Json -Compress")
    if not output:
        return []
    value = __import__("json").loads(output)
    return value if isinstance(value, list) else [value]


def process_list() -> list[dict[str, Any]]:
    if platform.system() != "Windows":
        return []
    output = _powershell("Get-Process | Select-Object Id,ProcessName,Path | ConvertTo-Json -Compress")
    if not output:
        return []
    value = __import__("json").loads(output)
    return value if isinstance(value, list) else [value]


def stop_process(pid: int, name: str) -> tuple[bool, str]:
    if platform.system() != "Windows":
        return False, "Process control is only supported on Windows."
    safe_name = name.replace("'", "''")
    output = _powershell(f"$p=Get-Process -Id {int(pid)} -ErrorAction Stop; if ($p.ProcessName -ne '{safe_name}') {{ throw 'process identity mismatch' }}; Stop-Process -Id {int(pid)} -ErrorAction Stop; 'stopped'")
    return True, output or "process stopped"


def startup_entries() -> list[dict[str, Any]]:
    if platform.system() != "Windows":
        return []
    output = _powershell("$p='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'; if (Test-Path $p) { (Get-ItemProperty $p | Get-Member -MemberType NoteProperty | ForEach-Object { [pscustomobject]@{Name=$_.Name; Command=(Get-ItemPropertyValue -Path $p -Name $_.Name); Location=$p} }) | ConvertTo-Json -Compress }")
    if not output:
        return []
    value = __import__("json").loads(output)
    return value if isinstance(value, list) else [value]


def disable_run_entry(name: str, source: str) -> dict[str, str]:
    if platform.system() != "Windows":
        raise RuntimeError("Startup control is only supported on Windows.")
    if source.lower() != "hkcu\\software\\microsoft\\windows\\currentversion\\run":
        raise RuntimeError("startup source is not allowlisted")
    safe_name = name.replace("'", "''")
    safe_source = source.replace("'", "''")
    script = f"$p='Registry::{safe_source}'; $previous=Get-ItemPropertyValue -Path $p -Name '{safe_name}' -ErrorAction Stop; Remove-ItemProperty -Path $p -Name '{safe_name}' -ErrorAction Stop; [pscustomobject]@{{previous=$previous}} | ConvertTo-Json -Compress"
    output = _powershell(script)
    value = __import__("json").loads(output) if output else {}
    return value if isinstance(value, dict) else {}


def restore_run_entry(name: str, command: str) -> None:
    if platform.system() != "Windows":
        return
    if not command:
        return
    safe_name = name.replace("'", "''")
    safe_command = command.replace("'", "''")
    _powershell(f"New-Item -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -Force | Out-Null; New-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -Name '{safe_name}' -Value '{safe_command}' -PropertyType String -Force | Out-Null")


def repair_system_files(*, scan_only: bool) -> tuple[bool, str]:
    if platform.system() != "Windows":
        return False, "Windows system-file servicing is unavailable on this platform."
    command = "sfc.exe /verifyonly" if scan_only else "sfc.exe /scannow"
    completed = subprocess.run(["cmd.exe", "/c", command], capture_output=True, text=True, timeout=900, check=False)
    detail = (completed.stdout or completed.stderr or "").strip()[-4000:]
    return completed.returncode == 0, detail


def network_reset() -> tuple[bool, str]:
    if platform.system() != "Windows":
        return False, "Windows network reset is unavailable on this platform."
    return False, "Network reset adapter is intentionally gated behind interactive high-risk confirmation."
