"""Tests for the mailroom actions."""

from __future__ import annotations

from typing import Any

import aiohttp
import pytest
import voluptuous as vol
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service import async_get_all_descriptions
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from yarl import URL

from custom_components.mailroom.const import DOMAIN

from . import BASE_URL, PARCELS, mock_api, parcel_json

NEW9_URL = f"{BASE_URL}/api/parcel/NEW9"
TQ1_URL = f"{BASE_URL}/api/parcel/TQ1"
TQ1_RECORD = {"@type": "ParcelDelivery", "trackingNumber": "TQ1"}


def _writes(aioclient_mock: AiohttpClientMocker) -> list[tuple[str, URL, Any]]:
    """The requests made so far that change something in mailroom."""
    return [
        (method, url, body)
        for method, url, body, _headers in aioclient_mock.mock_calls
        if method != "GET"
    ]


async def test_add_parcel_asks_mailroom_not_to_replace_a_record(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.get(NEW9_URL, status=404)
    aioclient_mock.put(NEW9_URL, status=201, json={})

    await hass.services.async_call(
        DOMAIN, "add_parcel", {"tracking_number": "NEW9"}, blocking=True
    )

    assert [
        headers
        for method, _url, _body, headers in aioclient_mock.mock_calls
        if method == "PUT"
    ] == [{"If-None-Match": "*"}]


async def test_actions_use_the_credentials_of_the_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Mailroom",
        data={CONF_URL: BASE_URL, "username": "someone", "password": "secret"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.delete(TQ1_URL, status=204)

    await hass.services.async_call(
        DOMAIN, "remove_parcel", {"tracking_number": "TQ1"}, blocking=True
    )

    # base64 of "someone:secret"
    assert {
        headers["Authorization"]
        for _method, _url, _body, headers in aioclient_mock.mock_calls
    } == {"Basic c29tZW9uZTpzZWNyZXQ="}


async def test_add_parcel_reports_a_record_filed_in_the_meantime(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    # Not there when looked for, but there by the time of the write.
    aioclient_mock.get(NEW9_URL, status=404)
    aioclient_mock.put(NEW9_URL, status=412, json={"error": "parcel already exists"})

    with pytest.raises(ServiceValidationError, match="already has a parcel NEW9"):
        await hass.services.async_call(
            DOMAIN, "add_parcel", {"tracking_number": "NEW9"}, blocking=True
        )


async def test_add_parcel_files_a_record_and_refreshes(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    config_entry: MockConfigEntry,
) -> None:
    freezer.move_to("2026-10-04 12:00:00+00:00")
    mock_api(
        aioclient_mock,
        {
            "current": [*PARCELS["current"], parcel_json("NEW9", "OnItsWay")],
            "previous": PARCELS["previous"],
        },
    )
    aioclient_mock.get(NEW9_URL, status=404)
    aioclient_mock.put(NEW9_URL, status=201, json={})

    await hass.services.async_call(
        DOMAIN,
        "add_parcel",
        {
            "tracking_number": " NEW9 ",
            "carrier": "dpd",
            "description": "Bicycle pump",
            "postcode": "CB1 2AB",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    assert _writes(aioclient_mock) == [
        (
            "PUT",
            URL(NEW9_URL),
            {
                "@type": "ParcelDelivery",
                "trackingNumber": "NEW9",
                "receivedAt": "2026-10-04T12:00:00+00:00",
                "deliveryStatus": "OnItsWay",
                "history": [
                    {
                        "seen_at": "2026-10-04T12:00:00+00:00",
                        "source": "home-assistant",
                        "deliveryStatus": "OnItsWay",
                    }
                ],
                "provider": {"@id": "dpd"},
                "description": "Bicycle pump",
                "deliveryPostalCode": "CB1 2AB",
            },
        )
    ]
    state = hass.states.get("sensor.mailroom_in_transit")
    assert state is not None
    assert state.state == "3"


async def test_add_parcel_with_only_a_tracking_number(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    config_entry: MockConfigEntry,
) -> None:
    freezer.move_to("2026-10-04 12:00:00+00:00")
    aioclient_mock.get(NEW9_URL, status=404)
    aioclient_mock.put(NEW9_URL, status=201, json={})

    await hass.services.async_call(
        DOMAIN, "add_parcel", {"tracking_number": "NEW9"}, blocking=True
    )

    assert _writes(aioclient_mock) == [
        (
            "PUT",
            URL(NEW9_URL),
            {
                "@type": "ParcelDelivery",
                "trackingNumber": "NEW9",
                "receivedAt": "2026-10-04T12:00:00+00:00",
                "deliveryStatus": "OnItsWay",
                "history": [
                    {
                        "seen_at": "2026-10-04T12:00:00+00:00",
                        "source": "home-assistant",
                        "deliveryStatus": "OnItsWay",
                    }
                ],
            },
        )
    ]


async def test_add_parcel_does_not_replace_an_existing_record(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.get(TQ1_URL, json=TQ1_RECORD)
    aioclient_mock.put(TQ1_URL, json={})

    with pytest.raises(ServiceValidationError, match="already has a parcel TQ1"):
        await hass.services.async_call(
            DOMAIN, "add_parcel", {"tracking_number": "TQ1"}, blocking=True
        )

    assert _writes(aioclient_mock) == []


@pytest.mark.parametrize("action", ["add_parcel", "refresh_parcel", "remove_parcel"])
@pytest.mark.parametrize("tracking_number", ["", "..", "TQ1/refresh", "TQ 1"])
async def test_an_invalid_tracking_number_never_reaches_mailroom(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    action: str,
    tracking_number: str,
) -> None:
    aioclient_mock.clear_requests()

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, action, {"tracking_number": tracking_number}, blocking=True
        )

    assert aioclient_mock.mock_calls == []


async def test_refresh_parcel_returns_what_mailroom_made_of_it(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.post(
        f"{TQ1_URL}/refresh", json={"outcome": "updated", "parcel": TQ1_RECORD}
    )

    response = await hass.services.async_call(
        DOMAIN,
        "refresh_parcel",
        {"tracking_number": "TQ1"},
        blocking=True,
        return_response=True,
    )

    assert response == {"outcome": "updated", "parcel": TQ1_RECORD}
    assert _writes(aioclient_mock) == [("POST", URL(f"{TQ1_URL}/refresh"), None)]


async def test_remove_parcel_deletes_the_record_and_refreshes(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    mock_api(
        aioclient_mock,
        {"current": [PARCELS["current"][0]], "previous": PARCELS["previous"]},
    )
    aioclient_mock.delete(TQ1_URL, status=204)

    await hass.services.async_call(
        DOMAIN, "remove_parcel", {"tracking_number": "TQ1"}, blocking=True
    )
    await hass.async_block_till_done()

    assert _writes(aioclient_mock) == [("DELETE", URL(TQ1_URL), None)]
    state = hass.states.get("sensor.mailroom_in_transit")
    assert state is not None
    assert state.state == "1"


@pytest.mark.parametrize(
    ("action", "method", "url"),
    [
        ("refresh_parcel", "post", f"{NEW9_URL}/refresh"),
        ("remove_parcel", "delete", NEW9_URL),
    ],
)
async def test_a_parcel_mailroom_does_not_have_is_a_validation_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    action: str,
    method: str,
    url: str,
) -> None:
    aioclient_mock.request(method, url, status=404)

    with pytest.raises(ServiceValidationError, match="^mailroom has no parcel NEW9$"):
        await hass.services.async_call(
            DOMAIN, action, {"tracking_number": "NEW9"}, blocking=True
        )


async def test_a_mailroom_that_is_down_is_an_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.delete(TQ1_URL, exc=aiohttp.ClientConnectionError("refused"))

    with pytest.raises(HomeAssistantError, match="Unable to reach"):
        await hass.services.async_call(
            DOMAIN, "remove_parcel", {"tracking_number": "TQ1"}, blocking=True
        )


async def test_actions_need_a_loaded_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    error = aiohttp.ClientConnectionError("refused")
    aioclient_mock.get(f"{BASE_URL}/api/parcels", exc=error)
    aioclient_mock.get(f"{BASE_URL}/api/stats", exc=error)
    entry = MockConfigEntry(domain=DOMAIN, title="Mailroom", data={CONF_URL: BASE_URL})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id) is False

    with pytest.raises(ServiceValidationError, match="There are 0 loaded"):
        await hass.services.async_call(
            DOMAIN, "remove_parcel", {"tracking_number": "TQ1"}, blocking=True
        )


async def test_actions_ask_which_mailroom_when_there_are_several(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    other_url = "http://other.test"
    mock_api(aioclient_mock, base_url=other_url)
    other = MockConfigEntry(domain=DOMAIN, title="Mailroom", data={CONF_URL: other_url})
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.delete(TQ1_URL, status=204)
    aioclient_mock.delete(f"{other_url}/api/parcel/TQ1", status=204)

    with pytest.raises(ServiceValidationError, match="There are 2 loaded"):
        await hass.services.async_call(
            DOMAIN, "remove_parcel", {"tracking_number": "TQ1"}, blocking=True
        )
    assert _writes(aioclient_mock) == []

    await hass.services.async_call(
        DOMAIN,
        "remove_parcel",
        {"tracking_number": "TQ1", "config_entry_id": other.entry_id},
        blocking=True,
    )

    assert _writes(aioclient_mock) == [
        ("DELETE", URL(f"{other_url}/api/parcel/TQ1"), None)
    ]

    with pytest.raises(ServiceValidationError, match="No loaded mailroom entry"):
        await hass.services.async_call(
            DOMAIN,
            "remove_parcel",
            {"tracking_number": "TQ1", "config_entry_id": "nonesuch"},
            blocking=True,
        )


async def test_add_parcel_offers_carriers_and_takes_others(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    descriptions = await async_get_all_descriptions(hass)

    selector = descriptions[DOMAIN]["add_parcel"]["fields"]["carrier"]["selector"]
    assert selector["select"]["custom_value"] is True
    assert {"label": "Royal Mail", "value": "royal-mail"} in selector["select"][
        "options"
    ]
