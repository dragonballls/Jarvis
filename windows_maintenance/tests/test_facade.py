from windows_maintenance.facade import MaintenanceFacade, is_maintenance_request


def test_diagnosis_request_is_recognized():
    assert is_maintenance_request("Diagnose my PC")


def test_diagnosis_is_read_only_on_non_windows(monkeypatch):
    import windows_maintenance.adapters as adapters
    monkeypatch.setattr(adapters, "diagnostics", lambda: {"platform": "test", "windows": False})
    response = MaintenanceFacade().diagnose()
    assert response.report is not None
    assert response.results == ()


def test_fix_request_does_not_claim_high_risk_repairs_completed(monkeypatch):
    import windows_maintenance.facade as facade
    monkeypatch.setattr(facade.DiagnosticCollector, "collect", lambda self: facade.DiagnosticCollector([lambda: {"platform": "test"}]).collect())
    response = MaintenanceFacade().handle("Fix whatever is wrong, but don't change anything important")
    assert response.results == ()
    assert any("high-risk" in item.lower() or "protected" in item.lower() for item in response.plan.skipped_risks)
