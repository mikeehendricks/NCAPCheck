from app.models import User

from .conftest import register_user


def test_user_registration_and_login(client, app):
    response = register_user(client)
    assert response.status_code == 200
    assert b"Vehicle register" in response.data
    with app.app_context():
        user = User.query.filter_by(email="owner@example.com").one()
        assert user.is_admin is False
        assert user.check_password("correct-horse-battery-1")
        assert not user.check_password("wrong-password")


def test_initial_admin_token_is_single_use(client, app):
    response = client.post("/setup-admin", data={
        "setup_token": "one-time-test-token",
        "email": "admin@example.com",
        "password": "a-long-secure-test-password",
        "confirm_password": "a-long-secure-test-password",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Admin panel" in response.data
    with app.app_context():
        admin = User.query.filter_by(email="admin@example.com").one()
        assert admin.is_admin is True
        assert User.query.filter_by(is_admin=True).count() == 1
    assert client.get("/setup-admin").status_code == 410


def test_login_ignores_external_and_backslash_next_urls(client):
    register_user(client)
    client.post("/logout")
    response = client.post("/login?next=//evil.example", data={
        "email": "owner@example.com",
        "password": "correct-horse-battery-1",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_invalid_admin_bootstrap_token_does_not_create_account(client, app):
    response = client.post("/setup-admin", data={
        "setup_token": "wrong-token",
        "email": "attacker@example.com",
        "password": "a-long-secure-test-password",
        "confirm_password": "a-long-secure-test-password",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Setup token is invalid" in response.data
    with app.app_context():
        assert User.query.filter_by(is_admin=True).count() == 0


def test_admin_endpoint_denies_standard_user(client):
    register_user(client)
    response = client.get("/admin")
    assert response.status_code == 403
    assert b"Access denied" in response.data
