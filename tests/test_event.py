"""Tests for the mailroom parcel event entity."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from . import BASE_URL, PARCELS, mock_api, parcel_json

ENTITY_ID = "event.mailroom_parcel_update"


@pytest.fixture
def fired(hass: HomeAssistant, config_entry: MockConfigEntry) -> list[dict[str, Any]]:
    """The attributes of every event the entity fires, in order."""
    events: list[dict[str, Any]] = []

    @callback
    def _record(event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        assert new_state is not None
        if "event_type" in new_state.attributes:
            events.append(
                {
                    key: new_state.attributes[key]
                    for key in ("event_type", "tracking_number", "previous_status")
                }
            )

    async_track_state_change_event(hass, ENTITY_ID, _record)
    return events


async def test_nothing_fires_for_parcels_already_there_at_startup(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    state = hass.states.get(ENTITY_ID)

    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes["event_types"] == [
        "scheduled",
        "on_its_way",
        "out_for_delivery",
        "delivered",
        "returned",
        "problem",
        "unknown",
    ]


async def test_nothing_fires_while_nothing_changes(
    tick: Callable[[], Awaitable[None]], fired: list[dict[str, Any]]
) -> None:
    await tick()

    assert fired == []


async def test_a_status_change_fires(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    tick: Callable[[], Awaitable[None]],
    fired: list[dict[str, Any]],
) -> None:
    delivered = parcel_json(
        "TQ1",
        "Delivered",
        description="Bicycle bell",
        merchant="Bell Shop",
        expected_arrival="2026-10-04",
        delivered_at="2026-10-04T15:00:00+00:00",
    )
    mock_api(
        aioclient_mock,
        {
            "current": [PARCELS["current"][0]],
            "previous": [delivered, *PARCELS["previous"]],
        },
    )

    await tick()

    assert fired == [
        {
            "event_type": "delivered",
            "tracking_number": "TQ1",
            "previous_status": "out_for_delivery",
        }
    ]
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert {
        key: value
        for key, value in state.attributes.items()
        if key not in ("event_types", "friendly_name", "icon")
    } == {
        "event_type": "delivered",
        "tracking_number": "TQ1",
        "status": "delivered",
        "carrier": "Royal Mail",
        "description": "Bicycle bell",
        "merchant": "Bell Shop",
        "tracking_url": None,
        "expected_arrival": "2026-10-04",
        "overdue": False,
        "previous_status": "out_for_delivery",
    }


async def test_a_new_parcel_fires_with_no_previous_status(
    aioclient_mock: AiohttpClientMocker,
    tick: Callable[[], Awaitable[None]],
    fired: list[dict[str, Any]],
) -> None:
    mock_api(
        aioclient_mock,
        {
            "current": [*PARCELS["current"], parcel_json("NEW9", "Scheduled")],
            "previous": PARCELS["previous"],
        },
    )

    await tick()

    assert fired == [
        {
            "event_type": "scheduled",
            "tracking_number": "NEW9",
            "previous_status": None,
        }
    ]


async def test_each_change_in_one_poll_fires_separately(
    aioclient_mock: AiohttpClientMocker,
    tick: Callable[[], Awaitable[None]],
    fired: list[dict[str, Any]],
) -> None:
    mock_api(
        aioclient_mock,
        {
            "current": [parcel_json("JD2", "OutForDelivery")],
            "previous": [parcel_json("TQ1", "Delivered"), *PARCELS["previous"]],
        },
    )

    await tick()

    assert fired == [
        {
            "event_type": "out_for_delivery",
            "tracking_number": "JD2",
            "previous_status": "on_its_way",
        },
        {
            "event_type": "delivered",
            "tracking_number": "TQ1",
            "previous_status": "out_for_delivery",
        },
    ]


async def test_a_parcel_dropping_off_the_dashboard_does_not_fire(
    aioclient_mock: AiohttpClientMocker,
    tick: Callable[[], Awaitable[None]],
    fired: list[dict[str, Any]],
) -> None:
    mock_api(aioclient_mock, {"current": PARCELS["current"], "previous": []})

    await tick()

    assert fired == []


async def test_an_outage_does_not_repeat_or_lose_events(
    aioclient_mock: AiohttpClientMocker,
    tick: Callable[[], Awaitable[None]],
    fired: list[dict[str, Any]],
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE_URL}/api/parcels", status=500)
    aioclient_mock.get(f"{BASE_URL}/api/stats", status=500)
    await tick()

    assert fired == []

    mock_api(
        aioclient_mock,
        {
            "current": [parcel_json("JD2", "Problem")],
            "previous": [parcel_json("TQ1", "Delivered"), *PARCELS["previous"]],
        },
    )
    await tick()
    await tick()

    assert fired == [
        {
            "event_type": "problem",
            "tracking_number": "JD2",
            "previous_status": "on_its_way",
        },
        {
            "event_type": "delivered",
            "tracking_number": "TQ1",
            "previous_status": "out_for_delivery",
        },
    ]
