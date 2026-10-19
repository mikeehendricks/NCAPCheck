"""Periodic scheduling logic. Current cycles create review tasks, not official results."""
from __future__ import annotations

from datetime import timedelta

from . import db
from .models import AuditEvent, ProviderResult, Setting, Vehicle, utcnow
from .providers import PROVIDERS, check_provider
from .settings import get_interval_hours


def run_due_checks(now=None, limit: int = 500) -> dict[str, int]:
    """Queue a manual review for each provider on every due vehicle.

    No plate or MV number is passed to provider adapters. At present the sites
    require interactive CAPTCHA/reCAPTCHA verification or block automated
    access, so an automated cycle must never claim a clear/violation result.
    """
    now = now or utcnow()
    interval = get_interval_hours()
    due_vehicles = (
        Vehicle.query.filter(Vehicle.next_check_at <= now)
        .order_by(Vehicle.next_check_at.asc())
        .limit(limit)
        .all()
    )
    scheduled = 0
    for vehicle in due_vehicles:
        for provider in PROVIDERS:
            outcome = check_provider(provider.key)
            result = ProviderResult.query.filter_by(
                vehicle_id=vehicle.id, provider_key=provider.key
            ).first()
            if result is None:
                result = ProviderResult(vehicle_id=vehicle.id, provider_key=provider.key)
                db.session.add(result)
            result.state = outcome.state
            result.message = outcome.message
            result.checked_at = now
        vehicle.last_check_at = now
        vehicle.next_check_at = now + timedelta(hours=interval)
        scheduled += 1

    heartbeat = db.session.get(Setting, "worker_last_heartbeat")
    if heartbeat is None:
        heartbeat = Setting(key="worker_last_heartbeat", value=now.isoformat(timespec="seconds"))
        db.session.add(heartbeat)
    else:
        heartbeat.value = now.isoformat(timespec="seconds")
    if scheduled:
        db.session.add(AuditEvent(event_type="scheduled_review", detail=f"Queued manual review for {scheduled} vehicle(s)."))
    db.session.commit()
    return {"vehicles_scheduled": scheduled, "provider_tasks": scheduled * len(PROVIDERS)}
