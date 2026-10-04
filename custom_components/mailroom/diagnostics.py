"""Diagnostics support for mailroom."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import MailroomConfigEntry

# Enough to tell whose parcels these are, and of no use in a bug report.
TO_REDACT = {"tracking_number", "tracking_url", "description", "merchant"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MailroomConfigEntry
) -> dict[str, Any]:
    """Return what the last poll fetched, without the identifying parts."""
    coordinator = entry.runtime_data
    return {
        "last_update_success": coordinator.last_update_success,
        "data": async_redact_data(asdict(coordinator.data), TO_REDACT),
    }
