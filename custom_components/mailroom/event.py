"""Event platform for mailroom."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.storage import Store

from .api import DeliveryStatus, Parcels
from .const import DOMAIN
from .coordinator import MailroomConfigEntry, MailroomCoordinator
from .entity import MailroomEntity, parcel_attributes

STORAGE_VERSION = 1
SAVE_DELAY = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MailroomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the mailroom event entity."""
    async_add_entities([ParcelEvent(entry.runtime_data, entry)])


def status_store(
    hass: HomeAssistant, entry: MailroomConfigEntry
) -> Store[dict[str, str]]:
    """Return the store holding the status last reported for each parcel."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")


def _statuses(parcels: Parcels) -> dict[str, str]:
    return {
        parcel.tracking_number: parcel.status.value
        for parcel in (*parcels.current, *parcels.previous)
    }


class ParcelEvent(MailroomEntity, EventEntity):
    """Fires when a parcel shows up or moves to another status.

    The event type is the status the parcel moved to. What was last reported
    is kept on disk, so a change that happens while Home Assistant is not
    running is reported by the first poll after it is back.
    """

    def __init__(
        self, coordinator: MailroomCoordinator, entry: MailroomConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "parcel")
        self._attr_event_types = [status.value for status in DeliveryStatus]
        self._store = status_store(coordinator.hass, entry)
        self._reported: dict[str, str] = {}

    async def async_added_to_hass(self) -> None:
        """Pick up where the last run left off."""
        stored = await self._store.async_load()
        if stored is None:
            # A new entry: the parcels already there are not news.
            self._set_reported(_statuses(self.coordinator.data.parcels))
        else:
            self._reported = stored
        await super().async_added_to_hass()

    def _set_reported(self, statuses: dict[str, str]) -> None:
        self._reported = statuses
        self._store.async_delay_save(lambda: self._reported, SAVE_DELAY)

    @callback
    def _handle_coordinator_update(self) -> None:
        # Automations only listen once Home Assistant has started, so a
        # change seen before then waits for the next poll.
        if self.hass.state is CoreState.running:
            self._report_changes()
        super()._handle_coordinator_update()

    def _report_changes(self) -> None:
        parcels = self.coordinator.data.parcels
        for parcel in (*parcels.current, *parcels.previous):
            before = self._reported.get(parcel.tracking_number)
            if before == parcel.status.value:
                continue
            self._trigger_event(
                parcel.status.value,
                {**parcel_attributes(parcel), "previous_status": before},
            )
            self.async_write_ha_state()
        statuses = _statuses(parcels)
        if statuses != self._reported:
            self._set_reported(statuses)
