import pytest
from cryptography.fernet import Fernet

from app import create_app, db


@pytest.fixture
def app(tmp_path):
    database_path = tmp_path / "test.sqlite3"
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key-for-ncapcheck",
        "APP_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
        "INSTANCE_PATH": str(tmp_path / "instance"),
        "WTF_CSRF_ENABLED": False,
        "ADMIN_SETUP_TOKEN": "one-time-test-token",
        "ENABLE_PANEL_UPDATES": False,
        "GITHUB_REPO": "mikeehendricks/NCAPCheck",
        "SCHEDULER_INTERVAL_MINUTES": 10,
    })
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def register_user(client, email="owner@example.com", password="correct-horse-battery-1"):
    return client.post("/register", data={
        "email": email,
        "password": password,
        "confirm_password": password,
    }, follow_redirects=True)


def add_vehicle(client, plate="ABC1234", mv_number="123456789012345"):
    return client.post("/vehicles/add", data={
        "plate": plate,
        "mv_number": mv_number,
        "label": "Daily car",
        "authorization_ack": "yes",
    }, follow_redirects=True)
