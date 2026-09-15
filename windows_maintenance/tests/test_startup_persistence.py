from windows_maintenance.startup import StartupManager


def test_reconcile_reports_recreated_block(monkeypatch):
    manager = StartupManager()
    monkeypatch.setattr(manager, "inventory", lambda: [{"Name": "Steam", "Location": "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"}])
    import windows_maintenance.startup as startup
    monkeypatch.setattr(startup.persistence, "load_policies", lambda: {
        "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run|steam": {
            "name": "Steam", "source": "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", "desired": "disabled"
        }
    })
    result = manager.reconcile_policies()
    assert result and result[0]["recreated"] is True
