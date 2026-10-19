from app.models import ManualReport, Vehicle
from app.providers import PROVIDERS

from .conftest import add_vehicle, register_user


def test_add_vehicle_encrypts_identifiers_at_rest(client, app):
    register_user(client)
    response = add_vehicle(client)
    assert response.status_code == 200
    assert b"ABC1234" in response.data
    with app.app_context():
        vehicle = Vehicle.query.one()
        assert vehicle.plate == "ABC1234"
        assert vehicle.mv_number == "123456789012345"
        assert "ABC1234" not in vehicle.plate_ciphertext
        assert "123456789012345" not in vehicle.mv_ciphertext


def test_invalid_vehicle_input_is_not_saved(client, app):
    register_user(client)
    response = add_vehicle(client, plate="<script>", mv_number="123")
    assert response.status_code == 200
    assert b"Enter a valid plate number" in response.data
    with app.app_context():
        assert Vehicle.query.count() == 0


def test_vehicle_isolation_between_users(client, app):
    register_user(client)
    add_vehicle(client)
    with app.app_context():
        vehicle_id = Vehicle.query.one().id
    other = app.test_client()
    register_user(other, email="other@example.com", password="another-long-password-123")
    assert other.get(f"/vehicles/{vehicle_id}").status_code == 404
    assert other.post(f"/vehicles/{vehicle_id}/delete").status_code == 404
    with app.app_context():
        assert Vehicle.query.count() == 1


def test_manual_report_is_encrypted_and_labeled_as_reported(client, app):
    register_user(client)
    add_vehicle(client)
    with app.app_context():
        vehicle_id = Vehicle.query.one().id
    response = client.post(f"/vehicles/{vehicle_id}/report", data={
        "provider_key": "quezon_city",
        "state": "violation_reported",
        "note": "Example note that should not be stored in plain text",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Violation reported manually" in response.data
    assert b"not an authority-verified result" in response.data
    with app.app_context():
        report = ManualReport.query.one()
        assert report.note == "Example note that should not be stored in plain text"
        assert "Example note" not in report.note_ciphertext


def test_vehicle_delete_removes_its_results(client, app):
    register_user(client)
    add_vehicle(client)
    with app.app_context():
        vehicle_id = Vehicle.query.one().id
    response = client.post(f"/vehicles/{vehicle_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        assert Vehicle.query.count() == 0
        assert ManualReport.query.count() == 0


def test_each_provider_is_listed(client, app):
    register_user(client)
    add_vehicle(client)
    with app.app_context():
        vehicle_id = Vehicle.query.one().id
    response = client.get(f"/vehicles/{vehicle_id}")
    assert response.status_code == 200
    for provider in PROVIDERS:
        assert provider.name.encode() in response.data
