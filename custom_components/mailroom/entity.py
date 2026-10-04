"""Base entity for the mailroom integration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.const import CONF_URL
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Parcel, Pickup
from .const import DOMAIN
from .coordinator import MailroomConfigEntry, MailroomCoordinator


class MailroomEntity(CoordinatorEntity[MailroomCoordinator]):
    """An entity backed by a mailroom instance."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: MailroomCoordinator, entry: MailroomConfigEntry, key: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=entry.data[CONF_URL],
        )


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


def _pickup_attributes(pickup: Pickup | None) -> dict[str, Any] | None:
    if pickup is None:
        return None
    return {
        "location": pickup.location,
        "code": pickup.code,
        "available_from": _iso(pickup.available_from),
        "available_through": _iso(pickup.available_through),
    }


def parcel_attributes(parcel: Parcel) -> dict[str, Any]:
    """Describe a parcel in a form that fits in state attributes."""
    return {
        "tracking_number": parcel.tracking_number,
        "status": parcel.status.value,
        "carrier": parcel.carrier,
        "description": parcel.description,
        "merchant": parcel.merchant,
        "tracking_url": parcel.tracking_url,
        "expected_arrival": (
            None
            if parcel.expected_arrival is None
            else parcel.expected_arrival.isoformat()
        ),
        "overdue": parcel.overdue,
        "delivered_at": _iso(parcel.delivered_at),
        "pickup": _pickup_attributes(parcel.pickup),
    }
