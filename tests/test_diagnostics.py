"""Tests for the mailroom diagnostics."""

from __future__ import annotations

from datetime import UTC, date, datetime

from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mailroom.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_leave_out_what_identifies_a_parcel(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    assert await async_get_config_entry_diagnostics(hass, config_entry) == {
        "last_update_success": True,
        "data": {
            "parcels": {
                "current": [
                    {
                        "tracking_number": REDACTED,
                        "status": "on_its_way",
                        "carrier": "dhl",
                        "description": None,
                        "merchant": None,
                        "tracking_url": REDACTED,
                        "expected_arrival": date(2026, 10, 3),
                        "overdue": True,
                        "delivered_at": None,
                        "last_polled": None,
                    },
                    {
                        "tracking_number": REDACTED,
                        "status": "out_for_delivery",
                        "carrier": "Royal Mail",
                        "description": REDACTED,
                        "merchant": REDACTED,
                        "tracking_url": None,
                        "expected_arrival": date(2026, 10, 4),
                        "overdue": False,
                        "delivered_at": None,
                        "last_polled": None,
                    },
                ],
                "previous": [
                    {
                        "tracking_number": REDACTED,
                        "status": "delivered",
                        "carrier": "PostNL",
                        "description": REDACTED,
                        "merchant": None,
                        "tracking_url": None,
                        "expected_arrival": None,
                        "overdue": False,
                        "delivered_at": datetime(2026, 10, 4, 14, 28, 56, tzinfo=UTC),
                        "last_polled": datetime(
                            2026, 10, 4, 14, 28, 56, 123456, tzinfo=UTC
                        ),
                    },
                ],
            },
            "stats": {"total": 40, "delivered": 37},
        },
    }
