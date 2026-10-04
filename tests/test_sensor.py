"""Tests for the mailroom sensors."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from . import BASE_URL, PARCELS, mock_api, parcel_json

JD2 = {
    "tracking_number": "JD2",
    "status": "on_its_way",
    "carrier": "dhl",
    "description": None,
    "merchant": None,
    "tracking_url": "https://www.dhl.com/en/express/tracking.html?AWB=JD2",
    "expected_arrival": "2026-10-03",
    "overdue": True,
}
TQ1 = {
    "tracking_number": "TQ1",
    "status": "out_for_delivery",
    "carrier": "Royal Mail",
    "description": "Bicycle bell",
    "merchant": "Bell Shop",
    "tracking_url": None,
    "expected_arrival": "2026-10-04",
    "overdue": False,
}


@pytest.fixture(autouse=True)
def the_day_tq1_is_due(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to("2026-10-04 12:00:00+00:00")


@pytest.mark.parametrize(
    ("entity_id", "count", "parcels"),
    [
        ("sensor.mailroom_in_transit", "2", [JD2, TQ1]),
        ("sensor.mailroom_out_for_delivery", "1", [TQ1]),
        ("sensor.mailroom_arriving_today", "1", [TQ1]),
        ("sensor.mailroom_overdue", "1", [JD2]),
    ],
)
async def test_parcel_list_sensors(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_id: str,
    count: str,
    parcels: list[dict[str, object]],
) -> None:
    state = hass.states.get(entity_id)

    assert state is not None
    assert state.state == count
    assert state.attributes["parcels"] == parcels
    assert state.attributes["unit_of_measurement"] == "parcels"


@pytest.mark.parametrize(
    ("entity_id", "count"),
    [
        ("sensor.mailroom_delivered", "37"),
        ("sensor.mailroom_total_parcels", "40"),
    ],
)
async def test_stats_sensors(
    hass: HomeAssistant, config_entry: MockConfigEntry, entity_id: str, count: str
) -> None:
    state = hass.states.get(entity_id)

    assert state is not None
    assert state.state == count


async def test_arriving_today_follows_the_configured_time_zone(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    tick: Callable[[], Awaitable[None]],
    config_entry: MockConfigEntry,
) -> None:
    # Still the 4th in UTC, but already the 5th in Amsterdam.
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    freezer.move_to("2026-10-04 23:30:00+00:00")
    mock_api(
        aioclient_mock,
        {
            "current": [
                parcel_json("TQ1", "OnItsWay", expected_arrival="2026-10-04"),
                parcel_json("3S3", "OnItsWay", expected_arrival="2026-10-05"),
            ],
            "previous": [],
        },
    )

    await tick()

    state = hass.states.get("sensor.mailroom_arriving_today")
    assert state is not None
    assert state.state == "1"
    assert [p["tracking_number"] for p in state.attributes["parcels"]] == ["3S3"]


async def test_sensors_follow_mailroom(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    tick: Callable[[], Awaitable[None]],
    config_entry: MockConfigEntry,
) -> None:
    mock_api(aioclient_mock, {"current": [], "previous": PARCELS["previous"]})

    await tick()

    state = hass.states.get("sensor.mailroom_in_transit")
    assert state is not None
    assert state.state == "0"
    assert state.attributes["parcels"] == []


async def test_sensors_are_unavailable_while_mailroom_is_down(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    tick: Callable[[], Awaitable[None]],
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE_URL}/api/parcels", status=500)
    aioclient_mock.get(f"{BASE_URL}/api/stats", status=500)

    await tick()

    state = hass.states.get("sensor.mailroom_in_transit")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE

    mock_api(aioclient_mock)
    await tick()

    state = hass.states.get("sensor.mailroom_in_transit")
    assert state is not None
    assert state.state == "2"
