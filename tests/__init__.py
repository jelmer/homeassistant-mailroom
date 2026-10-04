"""Tests for the mailroom integration."""

from __future__ import annotations

from typing import Any

from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

BASE_URL = "http://mailroom.test:8080"


def parcel_json(tracking_number: str, status: str, **fields: Any) -> dict[str, Any]:
    """Build a parcel the way `/api/parcels` serialises one."""
    return {
        "tracking_number": tracking_number,
        "status": status,
        "carrier": "Royal Mail",
        "description": None,
        "merchant": None,
        "tracking_url": None,
        "expected_arrival": None,
        "overdue": False,
        "delivered_at": None,
        "last_polled": None,
        **fields,
    }


def stats_json(**fields: int) -> dict[str, Any]:
    """Build a `/api/stats` document, with the parts the integration ignores."""
    return {
        "total": 0,
        "active": 0,
        "overdue": 0,
        "delivered": 0,
        "by_status": [],
        "by_carrier": [],
        "by_merchant": [],
        "deliveries_by_month": [],
        "delivery_time": None,
        **fields,
    }


# Modelled on what a mailroom instance holding three parcels answers.
PARCELS = {
    "current": [
        parcel_json(
            "JD2",
            "OnItsWay",
            carrier="dhl",
            expected_arrival="2026-10-03",
            overdue=True,
            tracking_url="https://www.dhl.com/en/express/tracking.html?AWB=JD2",
        ),
        parcel_json(
            "TQ1",
            "OutForDelivery",
            description="Bicycle bell",
            merchant="Bell Shop",
            expected_arrival="2026-10-04",
        ),
    ],
    "previous": [
        parcel_json(
            "3S3",
            "Delivered",
            carrier="PostNL",
            description="Stroopwafels",
            delivered_at="2026-10-04T14:28:56+00:00",
            last_polled="2026-10-04T14:28:56.123456789+00:00",
        ),
    ],
}

STATS = stats_json(total=40, active=2, overdue=1, delivered=37)


def mock_api(
    aioclient_mock: AiohttpClientMocker,
    parcels: dict[str, Any] = PARCELS,
    stats: dict[str, Any] = STATS,
    base_url: str = BASE_URL,
) -> None:
    """Make the mocked mailroom answer with these documents from now on."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{base_url}/api/parcels", json=parcels)
    aioclient_mock.get(f"{base_url}/api/stats", json=stats)
