from cryptography.fernet import Fernet

from app import create_app
from app.updates import request_system_update


def test_csrf_is_required_when_enabled(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "csrf-test-key",
        "APP_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'csrf.sqlite3'}",
        "INSTANCE_PATH": str(tmp_path / "csrf-instance"),
        "WTF_CSRF_ENABLED": True,
        "ADMIN_SETUP_TOKEN": "token",
    })
    response = app.test_client().post("/register", data={"email": "x@example.com"})
    assert response.status_code == 400


def test_updater_requires_explicit_enablement(app):
    with app.app_context():
        started, message = request_system_update()
    assert started is False
    assert "not enabled" in message
