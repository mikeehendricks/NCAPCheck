"""NCAPCheck application factory."""
from __future__ import annotations

import os
from datetime import UTC
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
from flask import Flask, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app(test_config: dict | None = None) -> Flask:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass
    instance_path = (test_config or {}).get("INSTANCE_PATH") or os.environ.get("INSTANCE_PATH")
    if instance_path:
        app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    else:
        app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", ""),
        APP_ENCRYPTION_KEY=os.environ.get("APP_ENCRYPTION_KEY", ""),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///ncapcheck.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        WTF_CSRF_ENABLED=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_env_bool("SESSION_COOKIE_SECURE", False),
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SECURE=_env_bool("SESSION_COOKIE_SECURE", False),
        PERMANENT_SESSION_LIFETIME=60 * 60 * 12,
        ADMIN_SETUP_TOKEN=os.environ.get("ADMIN_SETUP_TOKEN", ""),
        GITHUB_REPO=os.environ.get("GITHUB_REPO", "mikeehendricks/NCAPCheck"),
        APP_VERSION=(Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip(),
        ENABLE_PANEL_UPDATES=_env_bool("ENABLE_PANEL_UPDATES", False),
        UPDATE_SERVICE_COMMAND=["sudo", "-n", "/usr/bin/systemctl", "start", "ncapcheck-update.service"],
        SCHEDULER_INTERVAL_MINUTES=int(os.environ.get("SCHEDULER_INTERVAL_MINUTES", "10")),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is required. Run scripts/install-ubuntu.sh or set it in the environment.")
    encryption_key = app.config.get("APP_ENCRYPTION_KEY")
    if not encryption_key:
        raise RuntimeError("APP_ENCRYPTION_KEY is required. Generate a Fernet key and keep it secret.")
    try:
        Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("APP_ENCRYPTION_KEY must be a valid Fernet key.") from exc

    # SQLite is sufficient for a single-server installation. The installer stores
    # its database in /var/lib/ncapcheck and configures a single worker scheduler.
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:"):
        options = dict(app.config.get("SQLALCHEMY_ENGINE_OPTIONS", {}))
        connect_args = dict(options.get("connect_args", {}))
        connect_args.setdefault("check_same_thread", False)
        options["connect_args"] = connect_args
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = options

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "info"

    def manila_time(value):
        if value is None:
            return "—"
        if isinstance(value, str):
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(ZoneInfo("Asia/Manila")).strftime("%b %d, %Y · %I:%M %p")

    app.add_template_filter(manila_time, "manila_time")

    from . import models
    from .admin import bp as admin_bp
    from .auth import bp as auth_bp
    from .main import bp as main_bp
    from .settings import seed_settings

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session.get(models.User, int(user_id))
        except (TypeError, ValueError):
            return None

    @app.before_request
    def enforce_account_status():
        if current_user.is_authenticated and not current_user.is_active:
            from flask_login import logout_user
            logout_user()
            if request.endpoint not in {"auth.login", "static"}:
                return redirect(url_for("auth.login"))

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.route("/healthz")
    def healthz():
        return {"status": "ok", "service": "ncapcheck"}, 200

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("main.dashboard"))
        return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    with app.app_context():
        db.create_all()
        seed_settings()

    return app
