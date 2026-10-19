"""GitHub release checks and a fixed, administrator-triggered systemd updater."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests
from flask import current_app


@dataclass(frozen=True)
class UpdateInfo:
    status: str
    current_version: str
    latest_version: str = ""
    url: str = ""
    message: str = ""


def current_version() -> str:
    try:
        return (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def check_latest_release() -> UpdateInfo:
    repo = current_app.config.get("GITHUB_REPO", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or ""):
        return UpdateInfo("error", current_version(), message="GitHub repository setting is invalid.")
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        response = requests.get(
            url,
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            timeout=(3.05, 8),
        )
    except requests.RequestException:
        return UpdateInfo("unavailable", current_version(), message="Could not reach GitHub. Try again later.")
    if response.status_code == 404:
        return UpdateInfo("no_release", current_version(), message="No public GitHub release is published yet.")
    if response.status_code == 403:
        return UpdateInfo("rate_limited", current_version(), message="GitHub rate-limited the request. Try again later.")
    if response.status_code != 200:
        return UpdateInfo("unavailable", current_version(), message=f"GitHub returned HTTP {response.status_code}.")
    try:
        payload = response.json()
        tag = str(payload.get("tag_name", "")).strip()
        html_url = str(payload.get("html_url", "")).strip()
    except (ValueError, AttributeError):
        return UpdateInfo("error", current_version(), message="GitHub returned an invalid release response.")
    if not tag:
        return UpdateInfo("no_release", current_version(), message="The latest release has no version tag.")
    current = current_version()
    state = "up_to_date" if tag.lstrip("v") == current.lstrip("v") else "update_available"
    message = "You are on the latest published release." if state == "up_to_date" else "A newer release is available. Review its notes before applying."
    return UpdateInfo(state, current, tag, html_url, message)


def request_system_update() -> tuple[bool, str]:
    """Request only the fixed systemd unit; no command or path comes from user input."""
    if not current_app.config.get("ENABLE_PANEL_UPDATES", False):
        return False, "Panel updates are not enabled on this installation."
    command = current_app.config.get("UPDATE_SERVICE_COMMAND")
    if not isinstance(command, list) or not command:
        return False, "Update service command is not configured."
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False, "Could not start the updater. Check systemd and sudoers configuration."
    return True, "Update was queued. The app and background worker may restart shortly."
