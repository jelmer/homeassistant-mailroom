"""The mailroom integration."""

from __future__ import annotations

from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import MailroomClient
from .card import async_register_card, async_serve_card, async_unregister_card
from .const import DOMAIN
from .coordinator import MailroomConfigEntry, MailroomCoordinator
from .event import status_store
from .services import async_setup_services

PLATFORMS: list[Platform] = [Platform.EVENT, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the mailroom actions and dashboard card."""
    async_setup_services(hass)
    await async_serve_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MailroomConfigEntry) -> bool:
    """Set up mailroom from a config entry."""
    client = MailroomClient(async_get_clientsession(hass), entry.data[CONF_URL])
    coordinator = MailroomCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await async_register_card(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MailroomConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: MailroomConfigEntry) -> None:
    """Forget what was stored for a removed entry."""
    await status_store(hass, entry).async_remove()
    others = [
        other
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id
    ]
    if not others:
        await async_unregister_card(hass)
