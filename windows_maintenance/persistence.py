import json
import os
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Jarvis" / "windows_maintenance"
POLICY_FILE = STATE_DIR / "startup_policies.json"
AUDIT_FILE = STATE_DIR / "audit.jsonl"


def _load(path: Path) -> Any:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def load_policies() -> dict[str, dict[str, Any]]:
    value = _load(POLICY_FILE)
    return value if isinstance(value, dict) else {}


def save_policy(key: str, value: dict[str, Any]) -> None:
    policies = load_policies()
    policies[key] = value
    _write(POLICY_FILE, policies)


def remove_policy(key: str) -> None:
    policies = load_policies()
    policies.pop(key, None)
    _write(POLICY_FILE, policies)


def append_audit(record: dict[str, Any]) -> None:
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
