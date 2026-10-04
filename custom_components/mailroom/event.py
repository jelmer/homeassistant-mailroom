"""Event platform for mailroom."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import DeliveryStatus, Parcel, Parcels
from .coordinator import MailroomConfigEntry, MailroomCoordinator
from .entity import MailroomEntity, parcel_attributes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MailroomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the mailroom event entity."""
    async_add_entities([ParcelEvent(entry.runtime_data, entry)])


def _by_tracking_number(parcels: Parcels) -> dict[str, Parcel]:
    return {
        parcel.tracking_number: parcel
        for parcel in (*parcels.current, *parcels.previous)
    }


class ParcelEvent(MailroomEntity, EventEntity):
    """Fires when a parcel shows up or moves to another status.

    The event type is the status the parcel moved to. Changes that happen
    while Home Assistant is not running are not reported afterwards: the
    first poll only establishes what to compare later ones against.
    """

    def __init__(
        self, coordinator: MailroomCoordinator, entry: MailroomConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "parcel")
        self._attr_event_types = [status.value for status in DeliveryStatus]
        self._known = _by_tracking_number(coordinator.data.parcels)

    @callback
    def _handle_coordinator_update(self) -> None:
        previous = self._known
        self._known = _by_tracking_number(self.coordinator.data.parcels)
        for tracking_number, parcel in self._known.items():
            before = previous.get(tracking_number)
            if before is not None and before.status is parcel.status:
                continue
            self._trigger_event(
                parcel.status.value,
                {
                    **parcel_attributes(parcel),
                    "previous_status": None if before is None else before.status.value,
                },
            )
            self.async_write_ha_state()
        super()._handle_coordinator_update()
