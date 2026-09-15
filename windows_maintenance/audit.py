from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from .models import MaintenanceRecord

_STATE_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "Jarvis" / "windows_maintenance"
_AUDIT_FILE = _STATE_DIR / "audit.jsonl"


def append_record(record: MaintenanceRecord | dict[str, Any]) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = record.__dict__ if isinstance(record, MaintenanceRecord) else dict(record)
    with _AUDIT_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")


def new_record(operation: str, target_id: str, *, previous_state: dict[str, Any] | None = None, resulting_state: dict[str, Any] | None = None, verified: bool = False, rollback: dict[str, Any] | None = None) -> MaintenanceRecord:
    import uuid
    return MaintenanceRecord(
        correlation_id=uuid.uuid4().hex,
        timestamp=datetime.now(timezone.utc).isoformat(),
        operation=operation,
        target_id=target_id,
        previous_state=previous_state or {},
        resulting_state=resulting_state or {},
        verified=verified,
        rollback=rollback or {},
    )
