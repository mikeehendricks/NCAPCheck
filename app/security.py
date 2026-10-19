"""Small helpers for encrypting sensitive fields with the app's Fernet key."""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _fernet() -> Fernet:
    key = current_app.config["APP_ENCRYPTION_KEY"]
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_text(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        # Fail closed rather than accidentally displaying corrupted data.
        raise RuntimeError("Unable to decrypt stored data. Verify APP_ENCRYPTION_KEY and restore the matching key.") from exc
