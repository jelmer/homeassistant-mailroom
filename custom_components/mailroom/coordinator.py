"""DataUpdateCoordinator for mailroom."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MailroomClient, MailroomError, Parcels, Stats
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type MailroomConfigEntry = ConfigEntry[MailroomCoordinator]


@dataclass(frozen=True)
class MailroomData:
    """One poll's worth of mailroom state."""

    parcels: Parcels
    stats: Stats


class MailroomCoordinator(DataUpdateCoordinator[MailroomData]):
    """Coordinator to fetch parcels and statistics from mailroom."""

    def __init__(
        self, hass: HomeAssistant, entry: MailroomConfigEntry, client: MailroomClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> MailroomData:
        try:
            parcels, stats = await asyncio.gather(
                self.client.parcels(), self.client.stats()
            )
        except MailroomError as err:
            raise UpdateFailed(str(err)) from err
        return MailroomData(parcels=parcels, stats=stats)
