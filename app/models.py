"""Database models. Vehicle identifiers and check notes are encrypted at rest."""
from __future__ import annotations

from datetime import UTC, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .security import decrypt_text, encrypt_text


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    vehicles = db.relationship("Vehicle", back_populates="owner", cascade="all, delete-orphan", lazy="select")
    __table_args__ = (
        db.Index("uq_users_single_admin", "is_admin", unique=True, sqlite_where=(is_admin.is_(True))),
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User id={self.id} admin={self.is_admin}>"


class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    label = db.Column(db.String(60), nullable=False, default="")
    plate_ciphertext = db.Column(db.Text, nullable=False)
    mv_ciphertext = db.Column(db.Text, nullable=False)
    consented_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_check_at = db.Column(db.DateTime, nullable=True)
    next_check_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    owner = db.relationship("User", back_populates="vehicles")
    provider_results = db.relationship("ProviderResult", back_populates="vehicle", cascade="all, delete-orphan", lazy="select")
    manual_reports = db.relationship("ManualReport", back_populates="vehicle", cascade="all, delete-orphan", lazy="select")

    @property
    def plate(self) -> str:
        return decrypt_text(self.plate_ciphertext)

    @property
    def mv_number(self) -> str:
        return decrypt_text(self.mv_ciphertext)

    def set_identifiers(self, plate: str, mv_number: str) -> None:
        self.plate_ciphertext = encrypt_text(plate)
        self.mv_ciphertext = encrypt_text(mv_number)

    def __repr__(self) -> str:
        # Do not include registration details in logs or tracebacks.
        return f"<Vehicle id={self.id} user_id={self.user_id}>"


class ProviderResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_key = db.Column(db.String(50), nullable=False)
    state = db.Column(db.String(40), nullable=False, default="not_checked")
    message = db.Column(db.String(300), nullable=False, default="")
    checked_at = db.Column(db.DateTime, nullable=True)
    vehicle = db.relationship("Vehicle", back_populates="provider_results")
    __table_args__ = (db.UniqueConstraint("vehicle_id", "provider_key", name="uq_provider_result_vehicle"),)


class ManualReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vehicle_id = db.Column(db.Integer, db.ForeignKey("vehicle.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    provider_key = db.Column(db.String(50), nullable=False)
    state = db.Column(db.String(40), nullable=False)
    note_ciphertext = db.Column(db.Text, nullable=True)
    reported_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    vehicle = db.relationship("Vehicle", back_populates="manual_reports")
    reporter = db.relationship("User")

    @property
    def note(self) -> str:
        if not self.note_ciphertext:
            return ""
        return decrypt_text(self.note_ciphertext)

    def set_note(self, value: str) -> None:
        self.note_ciphertext = encrypt_text(value) if value else None


class Setting(db.Model):
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.String(500), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AuditEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    event_type = db.Column(db.String(60), nullable=False)
    detail = db.Column(db.String(240), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
