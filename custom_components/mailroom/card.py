"""The dashboard card that ships with the integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

CARD_FILENAME = "mailroom-parcels-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"


def _resources(hass: HomeAssistant) -> ResourceStorageCollection | None:
    """Return the dashboard resources, if they are ours to change.

    There are none without the dashboards themselves, and resources kept in
    YAML are for whoever maintains that file to add to.
    """
    if (lovelace := hass.data.get(LOVELACE_DATA)) is None:
        return None
    if not isinstance(lovelace.resources, ResourceStorageCollection):
        return None
    return lovelace.resources


async def _async_registered(resources: ResourceStorageCollection) -> list[dict]:
    """Return the resources that point at the card, whatever their version."""
    # Makes sure the collection has been read from storage.
    await resources.async_get_info()
    return [
        item
        for item in resources.async_items()
        if item["url"].partition("?")[0] == CARD_URL
    ]


async def async_serve_card(hass: HomeAssistant) -> None:
    """Make the card's script available over HTTP."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(Path(__file__).parent / "www" / CARD_FILENAME))]
    )


async def async_register_card(hass: HomeAssistant) -> None:
    """List the card among the dashboard resources, at its current version.

    A resource is loaded once the frontend is up. The other way of having a
    module loaded, `frontend.add_extra_js_url`, runs it before the frontend
    has swapped in its own element registry, which then knows nothing of the
    element the module defined.
    """
    if (resources := _resources(hass)) is None:
        return
    integration = await async_get_integration(hass, DOMAIN)
    # The version keeps browsers from holding on to an older release's card.
    resource = {"res_type": "module", "url": f"{CARD_URL}?v={integration.version}"}
    registered = await _async_registered(resources)
    if not registered:
        await resources.async_create_item(resource)
    elif registered[0]["url"] != resource["url"]:
        await resources.async_update_item(registered[0]["id"], resource)


async def async_unregister_card(hass: HomeAssistant) -> None:
    """Take the card off the dashboard resources again."""
    if (resources := _resources(hass)) is None:
        return
    for item in await _async_registered(resources):
        await resources.async_delete_item(item["id"])
