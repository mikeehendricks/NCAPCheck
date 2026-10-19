"""Application setting helpers and defaults."""
from __future__ import annotations

from . import db
from .models import Setting, utcnow

DEFAULT_SETTINGS = {
    "poll_interval_hours": "24",
    "allow_public_registration": "true",
    "worker_last_heartbeat": "",
}


def seed_settings() -> None:
    changed = False
    for key, value in DEFAULT_SETTINGS.items():
        if db.session.get(Setting, key) is None:
            db.session.add(Setting(key=key, value=value))
            changed = True
    if changed:
        db.session.commit()


def get_setting(key: str, default: str | None = None) -> str | None:
    row = db.session.get(Setting, key)
    if row is None:
        return default
    return row.value


def set_setting(key: str, value: str) -> None:
    row = db.session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
        db.session.add(row)
    else:
        row.value = value
        row.updated_at = utcnow()
    db.session.commit()


def get_interval_hours() -> int:
    try:
        return max(1, int(get_setting("poll_interval_hours", "24") or "24"))
    except (TypeError, ValueError):
        return 24


def get_registration_open() -> bool:
    return (get_setting("allow_public_registration", "true") or "true").lower() == "true"
