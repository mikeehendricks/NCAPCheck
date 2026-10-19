"""Authenticated vehicle dashboard and manual review workflow."""
from __future__ import annotations

import re

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import db
from .models import AuditEvent, ManualReport, Vehicle, utcnow
from .providers import PROVIDER_BY_KEY, PROVIDERS
from .settings import get_interval_hours

bp = Blueprint("main", __name__)


def owned_vehicle_or_404(vehicle_id: int) -> Vehicle:
    return Vehicle.query.filter_by(id=vehicle_id, user_id=current_user.id).first_or_404()


def latest_reports(vehicle: Vehicle) -> dict[str, ManualReport]:
    result: dict[str, ManualReport] = {}
    for report in sorted(vehicle.manual_reports, key=lambda item: (item.reported_at, item.id), reverse=True):
        result.setdefault(report.provider_key, report)
    return result


def consolidated_status(vehicle: Vehicle) -> tuple[str, str]:
    reports = latest_reports(vehicle)
    states = [report.state for report in reports.values()]
    if "violation_reported" in states:
        return "violation_reported", "Violation reported manually"
    if len(reports) == len(PROVIDERS) and all(state == "clear_reported" for state in states):
        return "clear_reported", "No violations reported manually"
    if reports:
        return "partial", "Partial manual results"
    return "review_required", "Portal review required"


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).upper()


@bp.route("/dashboard")
@login_required
def dashboard():
    vehicles = Vehicle.query.filter_by(user_id=current_user.id).order_by(Vehicle.created_at.desc()).all()
    summaries = [(vehicle, *consolidated_status(vehicle)) for vehicle in vehicles]
    pending = sum(1 for _, status, _ in summaries if status in {"review_required", "partial"})
    return render_template(
        "main/dashboard.html",
        summaries=summaries,
        pending=pending,
        interval_hours=get_interval_hours(),
        provider_count=len(PROVIDERS),
    )


@bp.route("/vehicles/add", methods=["POST"])
@login_required
def add_vehicle():
    plate = _normalize(request.form.get("plate", ""))
    mv_number = _normalize(request.form.get("mv_number", ""))
    label = (request.form.get("label", "") or "").strip()[:60]
    consent = request.form.get("authorization_ack") == "yes"
    if not re.fullmatch(r"[A-Z0-9-]{2,12}", plate):
        flash("Enter a valid plate number (2–12 letters, numbers, or hyphens).", "error")
    elif not re.fullmatch(r"[A-Z0-9-]{4,24}", mv_number):
        flash("Enter a valid MV file number (4–24 letters, numbers, or hyphens).", "error")
    elif not consent:
        flash("Confirm that you own the vehicle or are authorized to monitor it.", "error")
    else:
        vehicle = Vehicle(user_id=current_user.id, label=label, next_check_at=utcnow())
        vehicle.set_identifiers(plate, mv_number)
        db.session.add(vehicle)
        db.session.flush()
        db.session.add(AuditEvent(user_id=current_user.id, event_type="vehicle_added", detail="Encrypted vehicle identifiers saved."))
        db.session.commit()
        flash("Vehicle saved securely. Its first scheduled cycle will create manual-review tasks; it will not query protected portals automatically.", "success")
        return redirect(url_for("main.vehicle_detail", vehicle_id=vehicle.id))
    return redirect(url_for("main.dashboard"))


@bp.route("/vehicles/<int:vehicle_id>")
@login_required
def vehicle_detail(vehicle_id: int):
    vehicle = owned_vehicle_or_404(vehicle_id)
    report_map = latest_reports(vehicle)
    scheduled = {row.provider_key: row for row in vehicle.provider_results}
    status, status_label = consolidated_status(vehicle)
    return render_template(
        "main/vehicle_detail.html",
        vehicle=vehicle,
        providers=PROVIDERS,
        report_map=report_map,
        scheduled=scheduled,
        status=status,
        status_label=status_label,
        interval_hours=get_interval_hours(),
    )


@bp.route("/vehicles/<int:vehicle_id>/report", methods=["POST"])
@login_required
def save_manual_report(vehicle_id: int):
    vehicle = owned_vehicle_or_404(vehicle_id)
    provider_key = request.form.get("provider_key", "")
    state = request.form.get("state", "")
    note = (request.form.get("note", "") or "").strip()
    if provider_key not in PROVIDER_BY_KEY:
        abort(400)
    if state not in {"violation_reported", "clear_reported", "unable_to_verify"}:
        abort(400)
    if len(note) > 500:
        flash("The note must be 500 characters or fewer.", "error")
        return redirect(url_for("main.vehicle_detail", vehicle_id=vehicle.id))
    report = ManualReport(
        vehicle_id=vehicle.id,
        user_id=current_user.id,
        provider_key=provider_key,
        state=state,
        reported_at=utcnow(),
    )
    report.set_note(note)
    db.session.add(report)
    db.session.add(AuditEvent(user_id=current_user.id, event_type="manual_report", detail=f"Manual report saved for {PROVIDER_BY_KEY[provider_key].name}."))
    db.session.commit()
    flash("Manual report saved. This is your reported observation, not an authority-verified result.", "success")
    return redirect(url_for("main.vehicle_detail", vehicle_id=vehicle.id))


@bp.route("/vehicles/<int:vehicle_id>/check-now", methods=["POST"])
@login_required
def queue_vehicle_check(vehicle_id: int):
    vehicle = owned_vehicle_or_404(vehicle_id)
    vehicle.next_check_at = utcnow()
    db.session.add(AuditEvent(user_id=current_user.id, event_type="review_queued", detail="Manual review task queued."))
    db.session.commit()
    flash("Review task queued for the next worker cycle. This does not contact the portals or bypass verification.", "info")
    return redirect(url_for("main.vehicle_detail", vehicle_id=vehicle.id))


@bp.route("/vehicles/<int:vehicle_id>/delete", methods=["POST"])
@login_required
def delete_vehicle(vehicle_id: int):
    vehicle = owned_vehicle_or_404(vehicle_id)
    db.session.add(AuditEvent(user_id=current_user.id, event_type="vehicle_deleted", detail="Saved vehicle and related results deleted."))
    db.session.delete(vehicle)
    db.session.commit()
    flash("Vehicle and its check history were deleted.", "success")
    return redirect(url_for("main.dashboard"))
