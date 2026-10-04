"""Actions for the mailroom integration."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import voluptuous as vol
from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import (
    MailroomError,
    MailroomNotFoundError,
    MailroomParcelExistsError,
    is_valid_tracking_number,
)
from .const import DOMAIN
from .coordinator import MailroomConfigEntry, MailroomCoordinator

ATTR_TRACKING_NUMBER = "tracking_number"
ATTR_CARRIER = "carrier"
ATTR_DESCRIPTION = "description"
ATTR_POSTCODE = "postcode"

SERVICE_ADD_PARCEL = "add_parcel"
SERVICE_REFRESH_PARCEL = "refresh_parcel"
SERVICE_REMOVE_PARCEL = "remove_parcel"


def _tracking_number(value: Any) -> str:
    tracking_number: str = cv.string(value).strip()
    if not is_valid_tracking_number(tracking_number):
        raise vol.Invalid(
            "a tracking number may only contain letters, digits, '-' and '_'"
        )
    return tracking_number


_PARCEL_FIELDS = {
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Required(ATTR_TRACKING_NUMBER): _tracking_number,
}
PARCEL_SCHEMA = vol.Schema(_PARCEL_FIELDS)
ADD_PARCEL_SCHEMA = vol.Schema(
    {
        **_PARCEL_FIELDS,
        vol.Optional(ATTR_CARRIER): cv.string,
        vol.Optional(ATTR_DESCRIPTION): cv.string,
        vol.Optional(ATTR_POSTCODE): cv.string,
    }
)


def _coordinator(call: ServiceCall) -> MailroomCoordinator:
    """Find the mailroom instance an action is meant for."""
    entries: list[MailroomConfigEntry] = call.hass.config_entries.async_loaded_entries(
        DOMAIN
    )
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id is not None:
        for entry in entries:
            if entry.entry_id == entry_id:
                return entry.runtime_data
        raise ServiceValidationError(f"No loaded mailroom entry with id {entry_id}")
    if len(entries) != 1:
        raise ServiceValidationError(
            f"There are {len(entries)} loaded mailroom entries; "
            f"say which one to use with {ATTR_CONFIG_ENTRY_ID}"
        )
    return entries[0].runtime_data


@contextmanager
def _mailroom_errors() -> Generator[None]:
    """Report a failed request in the terms an action is expected to."""
    try:
        yield
    except (MailroomNotFoundError, MailroomParcelExistsError) as err:
        raise ServiceValidationError(str(err)) from err
    except MailroomError as err:
        raise HomeAssistantError(str(err)) from err


async def _add_parcel(call: ServiceCall) -> None:
    coordinator = _coordinator(call)
    with _mailroom_errors():
        await coordinator.client.add_parcel(
            call.data[ATTR_TRACKING_NUMBER],
            carrier=call.data.get(ATTR_CARRIER),
            description=call.data.get(ATTR_DESCRIPTION),
            postcode=call.data.get(ATTR_POSTCODE),
        )
    await coordinator.async_request_refresh()


async def _refresh_parcel(call: ServiceCall) -> ServiceResponse:
    coordinator = _coordinator(call)
    with _mailroom_errors():
        result = await coordinator.client.refresh_parcel(
            call.data[ATTR_TRACKING_NUMBER]
        )
    await coordinator.async_request_refresh()
    return {"outcome": result.outcome, "parcel": result.parcel}


async def _remove_parcel(call: ServiceCall) -> None:
    coordinator = _coordinator(call)
    with _mailroom_errors():
        await coordinator.client.remove_parcel(call.data[ATTR_TRACKING_NUMBER])
    await coordinator.async_request_refresh()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the mailroom actions."""
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_PARCEL, _add_parcel, schema=ADD_PARCEL_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_PARCEL,
        _refresh_parcel,
        schema=PARCEL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_PARCEL, _remove_parcel, schema=PARCEL_SCHEMA
    )
