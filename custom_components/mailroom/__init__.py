"""The mailroom integration."""

from __future__ import annotations

from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MailroomClient
from .coordinator import MailroomConfigEntry, MailroomCoordinator
from .event import status_store

PLATFORMS: list[Platform] = [Platform.EVENT, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: MailroomConfigEntry) -> bool:
    """Set up mailroom from a config entry."""
    client = MailroomClient(async_get_clientsession(hass), entry.data[CONF_URL])
    coordinator = MailroomCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MailroomConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: MailroomConfigEntry) -> None:
    """Forget what was stored for a removed entry."""
    await status_store(hass, entry).async_remove()
