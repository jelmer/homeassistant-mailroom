"""Tests for serving and registering the dashboard card."""

from __future__ import annotations

from http import HTTPStatus

from homeassistant.components.lovelace import LovelaceData
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE
from homeassistant.components.lovelace.dashboard import LovelaceStorage
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.mailroom.card import (
    async_register_card,
    async_unregister_card,
)
from custom_components.mailroom.const import DOMAIN

CARD_URL = "/mailroom/mailroom-parcels-card.js"


async def test_the_card_is_served(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    client = await hass_client()

    response = await client.get(CARD_URL)

    assert response.status == HTTPStatus.OK
    assert response.content_type == "text/javascript"
    assert 'customElements.define("mailroom-parcels-card"' in await response.text()


def _dashboard_resources(hass: HomeAssistant) -> ResourceStorageCollection:
    resources = ResourceStorageCollection(hass, LovelaceStorage(hass, None))
    hass.data[LOVELACE_DATA] = LovelaceData(
        resource_mode=MODE_STORAGE,
        dashboards={},
        resources=resources,
        yaml_dashboards={},
    )
    return resources


async def test_the_card_is_listed_once_and_follows_the_version(
    hass: HomeAssistant,
) -> None:
    resources = _dashboard_resources(hass)
    stale = await resources.async_create_item(
        {"res_type": "module", "url": f"{CARD_URL}?v=0.0.1"}
    )

    await async_register_card(hass)
    await async_register_card(hass)

    assert resources.async_items() == [
        {"id": stale["id"], "type": "module", "url": f"{CARD_URL}?v=0.1.0"}
    ]


async def test_the_card_is_taken_off_the_list_again(hass: HomeAssistant) -> None:
    resources = _dashboard_resources(hass)
    other = await resources.async_create_item(
        {"res_type": "module", "url": "/local/other-card.js"}
    )
    await async_register_card(hass)

    await async_unregister_card(hass)

    assert resources.async_items() == [other]


async def test_registering_without_dashboards_does_nothing(hass: HomeAssistant) -> None:
    await async_register_card(hass)
    await async_unregister_card(hass)
