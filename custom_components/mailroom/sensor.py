"""Sensor platform for mailroom."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import DeliveryStatus, Parcel, Parcels, Stats
from .coordinator import MailroomConfigEntry, MailroomCoordinator
from .entity import MailroomEntity, parcel_attributes

UNIT_PARCELS = "parcels"


@dataclass(frozen=True, kw_only=True)
class ParcelListSensorDescription(SensorEntityDescription):
    """A sensor counting a selection of parcels, which it lists as attributes."""

    parcels_fn: Callable[[Parcels], list[Parcel]]


@dataclass(frozen=True, kw_only=True)
class StatsSensorDescription(SensorEntityDescription):
    """A sensor reporting one of mailroom's aggregate figures."""

    value_fn: Callable[[Stats], int]


def _with_status(status: DeliveryStatus) -> Callable[[Parcels], list[Parcel]]:
    return lambda parcels: [
        parcel for parcel in parcels.current if parcel.status is status
    ]


def _in_transit(parcels: Parcels) -> list[Parcel]:
    """Parcels on their way whose status mailroom still vouches for.

    mailroom reports a parcel as unknown once it has gone without news for
    long enough. Such a parcel never leaves `current`, so counting it would
    keep these sensors above zero for good.
    """
    return [
        parcel
        for parcel in parcels.current
        if parcel.status is not DeliveryStatus.UNKNOWN
    ]


def _arriving_today(parcels: Parcels) -> list[Parcel]:
    today = dt_util.now().date()
    return [
        parcel for parcel in _in_transit(parcels) if parcel.expected_arrival == today
    ]


PARCEL_LIST_SENSORS = (
    ParcelListSensorDescription(
        key="in_transit",
        parcels_fn=_in_transit,
    ),
    ParcelListSensorDescription(
        key="out_for_delivery",
        parcels_fn=_with_status(DeliveryStatus.OUT_FOR_DELIVERY),
    ),
    ParcelListSensorDescription(
        key="arriving_today",
        parcels_fn=_arriving_today,
    ),
    ParcelListSensorDescription(
        key="overdue",
        parcels_fn=lambda parcels: [
            parcel for parcel in _in_transit(parcels) if parcel.overdue
        ],
    ),
    ParcelListSensorDescription(
        key="problem",
        parcels_fn=_with_status(DeliveryStatus.PROBLEM),
    ),
    ParcelListSensorDescription(
        key="unknown",
        parcels_fn=_with_status(DeliveryStatus.UNKNOWN),
    ),
)

STATS_SENSORS = (
    StatsSensorDescription(
        key="delivered",
        value_fn=lambda stats: stats.delivered,
    ),
    StatsSensorDescription(
        key="total",
        value_fn=lambda stats: stats.total,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MailroomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up mailroom sensor entities."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        ParcelListSensor(coordinator, entry, description)
        for description in PARCEL_LIST_SENSORS
    ]
    entities.extend(
        StatsSensor(coordinator, entry, description) for description in STATS_SENSORS
    )
    async_add_entities(entities)


class ParcelListSensor(MailroomEntity, SensorEntity):
    """The number of parcels matching some condition."""

    entity_description: ParcelListSensorDescription
    _attr_native_unit_of_measurement = UNIT_PARCELS
    _attr_state_class = SensorStateClass.MEASUREMENT
    # The list grows with the number of parcels and would bloat the recorder.
    _unrecorded_attributes = frozenset({"parcels"})

    def __init__(
        self,
        coordinator: MailroomCoordinator,
        entry: MailroomConfigEntry,
        description: ParcelListSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def _parcels(self) -> list[Parcel]:
        return self.entity_description.parcels_fn(self.coordinator.data.parcels)

    @property
    def native_value(self) -> int:
        """Return how many parcels match."""
        return len(self._parcels)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the matching parcels."""
        return {"parcels": [parcel_attributes(parcel) for parcel in self._parcels]}


class StatsSensor(MailroomEntity, SensorEntity):
    """A count over every record mailroom has on disk."""

    entity_description: StatsSensorDescription
    _attr_native_unit_of_measurement = UNIT_PARCELS
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self,
        coordinator: MailroomCoordinator,
        entry: MailroomConfigEntry,
        description: StatsSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int:
        """Return the figure."""
        return self.entity_description.value_fn(self.coordinator.data.stats)
