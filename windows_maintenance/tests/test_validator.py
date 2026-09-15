import pytest

from windows_maintenance.models import MaintenanceAction, RiskClass
from windows_maintenance.validator import validate_action


def test_process_stop_requires_pid():
    with pytest.raises(ValueError):
        validate_action(MaintenanceAction("process.stop", "steam.exe", {}, RiskClass.REVERSIBLE_LOW_RISK))


def test_shell_syntax_is_rejected_from_arguments():
    with pytest.raises(ValueError):
        validate_action(MaintenanceAction("startup.disable", "Steam", {"name": "Steam", "source": "HKCU; powershell.exe"}, RiskClass.REVERSIBLE_MEDIUM_RISK))
