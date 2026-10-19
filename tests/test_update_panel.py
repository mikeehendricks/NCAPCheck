from types import SimpleNamespace

from app import updates
from app.updates import check_latest_release

from .conftest import add_vehicle, register_user


def bootstrap_admin(client):
    return client.post("/setup-admin", data={
        "setup_token": "one-time-test-token",
        "email": "admin@example.com",
        "password": "a-long-secure-test-password",
        "confirm_password": "a-long-secure-test-password",
    })


def test_admin_panel_does_not_expose_vehicle_identifiers(client):
    register_user(client)
    add_vehicle(client)
    bootstrap_admin(client)
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"ABC1234" not in response.data
    assert b"123456789012345" not in response.data


def test_release_check_uses_github_release_metadata_only(app, monkeypatch):
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"tag_name": "v0.1.0", "html_url": "https://github.com/mikeehendricks/NCAPCheck/releases/tag/v0.1.0"},
    )
    called = {}

    def fake_get(url, **kwargs):
        called["url"] = url
        called.update(kwargs)
        return response

    monkeypatch.setattr(updates.requests, "get", fake_get)
    with app.app_context():
        info = check_latest_release()
    assert info.status == "up_to_date"
    assert info.latest_version == "v0.1.0"
    assert called["url"] == "https://api.github.com/repos/mikeehendricks/NCAPCheck/releases/latest"
    assert called["timeout"] == (3.05, 8)


def test_admin_apply_update_invokes_only_the_fixed_systemd_command(client, app, monkeypatch):
    bootstrap_admin(client)
    app.config["ENABLE_PANEL_UPDATES"] = True
    fixed_command = ["sudo", "-n", "/usr/bin/systemctl", "start", "ncapcheck-update.service"]
    app.config["UPDATE_SERVICE_COMMAND"] = fixed_command
    observed = {}

    def fake_popen(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(updates.subprocess, "Popen", fake_popen)
    response = client.post("/admin/update", data={"action": "apply"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Update was queued" in response.data
    assert observed["command"] == fixed_command
    assert "shell" not in observed["kwargs"]
