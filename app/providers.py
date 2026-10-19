"""Provider registry and honest, manual-verification-only adapters.

The listed government portals use interactive bot protection or deny automated
access from this server. This module intentionally does not submit plates,
MV file numbers, solve CAPTCHAs, or scrape protected pages. If an authority
publishes an approved API, a provider adapter can be added here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    url: str
    city: str
    mode: str = "manual"


@dataclass(frozen=True)
class CheckOutcome:
    state: str
    message: str


PROVIDERS = (
    Provider("quezon_city", "Quezon City NCAP", "https://nocontact.quezoncity.gov.ph/check-violations", "Quezon City"),
    Provider("manila", "GoManila No Contact", "https://www.gomanila.com/nocontact", "Manila"),
    Provider("paranaque", "Parañaque City NCAP", "https://paranaquecity.nocontact.ph/check-violations", "Parañaque"),
    Provider("san_juan", "San Juan City NCAP", "https://nocontact.sanjuancity.gov.ph/check-violations", "San Juan"),
    Provider("mmda", "MMDA May Huli Ka", "https://mayhulika.mmda.gov.ph/", "MMDA"),
)

PROVIDER_BY_KEY = {provider.key: provider for provider in PROVIDERS}
MANUAL_CHECK_MESSAGE = (
    "Interactive verification is required or no approved public lookup API is configured. "
    "Open the official portal and confirm the result manually."
)


def check_provider(provider_key: str) -> CheckOutcome:
    """Return a manual-verification task without contacting a protected portal."""
    if provider_key not in PROVIDER_BY_KEY:
        raise KeyError(f"Unknown provider: {provider_key}")
    return CheckOutcome(state="manual_required", message=MANUAL_CHECK_MESSAGE)
