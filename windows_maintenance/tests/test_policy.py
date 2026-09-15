from windows_maintenance.models import MaintenanceAction, RiskClass
from windows_maintenance.policy import MaintenancePolicy


def test_jarvis_is_protected():
    action = MaintenanceAction("process.stop", "Jarvis.exe", {"pid": 1}, RiskClass.REVERSIBLE_LOW_RISK)
    assert not MaintenancePolicy().evaluate(action).allowed


def test_user_app_cleanup_requires_explicit_intent():
    action = MaintenanceAction("process.stop", "steam.exe", {"pid": 2}, RiskClass.REVERSIBLE_LOW_RISK)
    policy = MaintenancePolicy()
    assert not policy.evaluate(action).allowed
    assert policy.evaluate(action, explicit_user_request=True).allowed


def test_unknown_operation_is_denied():
    action = MaintenanceAction("shell.exec", "x", {}, RiskClass.HIGH_RISK)
    assert not MaintenancePolicy().evaluate(action).allowed
