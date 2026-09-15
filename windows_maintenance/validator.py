from .models import MaintenanceAction

ALLOWED_ARGS = {
    "process.stop": {"pid"},
    "startup.disable": {"name", "source"},
    "startup.enable": {"name", "source"},
    "system.files.restore": set(),
    "network.reset": set(),
    "application.repair": {"name"},
}


def validate_action(action: MaintenanceAction) -> MaintenanceAction:
    allowed = ALLOWED_ARGS.get(action.operation)
    if allowed is None:
        raise ValueError(f"unsupported operation: {action.operation}")
    if action.operation == "process.stop" and not isinstance(action.arguments.get("pid"), int):
        raise ValueError("process.stop requires integer pid")
    if action.operation.startswith("startup."):
        if not str(action.arguments.get("name", "")).strip() or not str(action.arguments.get("source", "")).strip():
            raise ValueError("startup operation requires name and source")
    for key in action.arguments:
        if key not in allowed:
            raise ValueError(f"unsupported argument '{key}' for {action.operation}")
        if isinstance(action.arguments[key], str) and any(x in action.arguments[key].lower() for x in ("powershell", "invoke-expression", ";", "&&", "|")):
            raise ValueError("shell injection is not an allowed maintenance argument")
    return action
