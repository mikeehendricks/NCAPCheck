"""Administrator-only settings and controlled update panel."""
from __future__ import annotations

from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from . import db
from .models import AuditEvent, ManualReport, ProviderResult, User, Vehicle
from .providers import PROVIDERS
from .settings import (
    get_interval_hours,
    get_registration_open,
    get_setting,
    set_setting,
)
from .updates import check_latest_release, current_version, request_system_update

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@bp.route("", methods=["GET"])
@admin_required
def index():
    heartbeat = get_setting("worker_last_heartbeat", "") or ""
    return render_template(
        "admin/index.html",
        user_count=User.query.count(),
        vehicle_count=Vehicle.query.count(),
        result_count=ProviderResult.query.count(),
        manual_report_count=ManualReport.query.count(),
        poll_interval_hours=get_interval_hours(),
        registration_open=get_registration_open(),
        heartbeat=heartbeat,
        providers=PROVIDERS,
        current_version=current_version(),
        updates_enabled=bool(current_app.config.get("ENABLE_PANEL_UPDATES", False)),
        github_repo=current_app.config.get("GITHUB_REPO", ""),
    )


@bp.route("/settings", methods=["POST"])
@admin_required
def save_settings():
    try:
        interval = int(request.form.get("poll_interval_hours", "24"))
    except (TypeError, ValueError):
        interval = 0
    if not 6 <= interval <= 168:
        flash("Review interval must be between 6 and 168 hours.", "error")
        return redirect(url_for("admin.index"))
    allow_registration = request.form.get("allow_public_registration") == "yes"
    set_setting("poll_interval_hours", str(interval))
    set_setting("allow_public_registration", "true" if allow_registration else "false")
    db.session.add(AuditEvent(user_id=current_user.id, event_type="admin_settings", detail="Global schedule and registration settings changed."))
    db.session.commit()
    flash("Administrator settings saved.", "success")
    return redirect(url_for("admin.index"))


@bp.route("/update", methods=["POST"])
@admin_required
def update_action():
    action = request.form.get("action", "")
    if action == "check":
        info = check_latest_release()
        message = f"Current version: {info.current_version}. {info.message}"
        if info.latest_version:
            message += f" Latest release: {info.latest_version}."
        if info.url:
            message += f" Notes: {info.url}"
        flash(message, "info" if info.status in {"up_to_date", "no_release"} else "warning")
        db.session.add(AuditEvent(user_id=current_user.id, event_type="update_check", detail=f"GitHub update check: {info.status}."))
        db.session.commit()
        return redirect(url_for("admin.index"))
    if action == "apply":
        started, message = request_system_update()
        flash(message, "success" if started else "error")
        db.session.add(AuditEvent(user_id=current_user.id, event_type="update_apply", detail="Panel update queued." if started else "Panel update could not be queued."))
        db.session.commit()
        return redirect(url_for("admin.index"))
    abort(400)
