"""Login, public user registration, and single-use administrator bootstrap."""
from __future__ import annotations

import hmac
import re
from urllib.parse import urlparse

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
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func

from . import db
from .models import AuditEvent, User
from .settings import get_registration_open, get_setting, set_setting

bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _clean_email(value: str) -> str:
    return (value or "").strip().lower()


def _safe_next(target: str | None) -> bool:
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return False
    parsed = urlparse(target)
    return not parsed.netloc and parsed.scheme == ""


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = _clean_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        user = User.query.filter(func.lower(User.email) == email).first() if email else None
        if user is None or not user.is_active or not user.check_password(password):
            flash("Email or password is incorrect.", "error")
        else:
            login_user(user, remember=request.form.get("remember") == "yes")
            db.session.add(AuditEvent(user_id=user.id, event_type="login", detail="Successful sign-in."))
            db.session.commit()
            next_url = request.args.get("next")
            return redirect(next_url if _safe_next(next_url) else url_for("main.dashboard"))
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        db.session.add(AuditEvent(user_id=current_user.id, event_type="logout", detail="User signed out."))
        db.session.commit()
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if not get_registration_open():
        abort(403)
    if request.method == "POST":
        email = _clean_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not EMAIL_RE.fullmatch(email) or len(email) > 254:
            flash("Enter a valid email address.", "error")
        elif len(password) < 12:
            flash("Use a password with at least 12 characters.", "error")
        elif password != confirm:
            flash("The passwords do not match.", "error")
        elif User.query.filter(func.lower(User.email) == email).first():
            flash("An account with that email already exists.", "error")
        else:
            user = User(email=email, is_admin=False)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            db.session.add(AuditEvent(user_id=user.id, event_type="registration", detail="User account registered."))
            db.session.commit()
            login_user(user)
            flash("Account created. You can now add a vehicle.", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("auth/register.html")


@bp.route("/setup-admin", methods=["GET", "POST"])
def setup_admin():
    """Bootstrap exactly one admin with the random token printed by the installer."""
    token = current_app.config.get("ADMIN_SETUP_TOKEN", "")
    consumed = (get_setting("admin_bootstrap_used", "false") or "false").lower() == "true"
    if consumed or User.query.filter_by(is_admin=True).first() is not None:
        abort(410)
    if not token:
        abort(404)
    if request.method == "POST":
        supplied = request.form.get("setup_token", "")
        email = _clean_email(request.form.get("email", ""))
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not hmac.compare_digest(str(supplied), str(token)):
            flash("Setup token is invalid.", "error")
        elif not EMAIL_RE.fullmatch(email) or len(email) > 254:
            flash("Enter a valid email address.", "error")
        elif len(password) < 12:
            flash("Use a password with at least 12 characters.", "error")
        elif password != confirm:
            flash("The passwords do not match.", "error")
        elif User.query.filter(func.lower(User.email) == email).first():
            flash("An account with that email already exists.", "error")
        else:
            admin = User(email=email, is_admin=True)
            admin.set_password(password)
            db.session.add(admin)
            db.session.flush()
            db.session.add(AuditEvent(user_id=admin.id, event_type="admin_bootstrap", detail="One-time administrator setup completed."))
            db.session.commit()
            set_setting("admin_bootstrap_used", "true")
            login_user(admin)
            flash("Administrator account created. The bootstrap link is now closed.", "success")
            return redirect(url_for("admin.index"))
    return render_template("auth/setup_admin.html")
