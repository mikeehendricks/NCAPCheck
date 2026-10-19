from datetime import timedelta

from app import db
from app.checks import run_due_checks
from app.models import ProviderResult, Setting, Vehicle, utcnow
from app.providers import PROVIDERS
from app.settings import get_setting

from .conftest import add_vehicle, register_user


def test_scheduler_queues_manual_tasks_for_each_portal_without_lookup(client, app):
    register_user(client)
    add_vehicle(client)
    with app.app_context():
        vehicle = Vehicle.query.one()
        result = run_due_checks(now=utcnow())
        assert result == {"vehicles_scheduled": 1, "provider_tasks": len(PROVIDERS)}
        provider_results = ProviderResult.query.order_by(ProviderResult.provider_key).all()
        assert len(provider_results) == len(PROVIDERS)
        assert {row.state for row in provider_results} == {"manual_required"}
        assert all("captcha" in row.message.lower() or "interactive verification" in row.message.lower() for row in provider_results)
        next_check = vehicle.next_check_at
        assert next_check > vehicle.last_check_at
        assert run_due_checks(now=vehicle.last_check_at + timedelta(minutes=1))["vehicles_scheduled"] == 0
        assert Setting.query.filter_by(key="worker_last_heartbeat").one().value


def test_admin_can_change_interval_and_close_registration(client, app):
    client.post("/setup-admin", data={
        "setup_token": "one-time-test-token",
        "email": "admin@example.com",
        "password": "a-long-secure-test-password",
        "confirm_password": "a-long-secure-test-password",
    })
    response = client.post("/admin/settings", data={
        "poll_interval_hours": "48",
        # unchecked checkbox means registration is closed
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Administrator settings saved" in response.data
    with app.app_context():
        assert get_setting("poll_interval_hours") == "48"
        assert get_setting("allow_public_registration") == "false"


def test_admin_rejects_unsafe_interval(client):
    client.post("/setup-admin", data={
        "setup_token": "one-time-test-token",
        "email": "admin@example.com",
        "password": "a-long-secure-test-password",
        "confirm_password": "a-long-secure-test-password",
    })
    response = client.post("/admin/settings", data={"poll_interval_hours": "1"}, follow_redirects=True)
    assert b"between 6 and 168 hours" in response.data


def test_queue_now_only_moves_next_check_to_due(client, app):
    register_user(client)
    add_vehicle(client)
    with app.app_context():
        vehicle_id = Vehicle.query.one().id
        Vehicle.query.one().next_check_at = utcnow() + timedelta(days=1)
        db.session.commit()
    response = client.post(f"/vehicles/{vehicle_id}/check-now", follow_redirects=True)
    assert response.status_code == 200
    assert b"does not contact the portals" in response.data
    with app.app_context():
        assert Vehicle.query.one().next_check_at <= utcnow()
