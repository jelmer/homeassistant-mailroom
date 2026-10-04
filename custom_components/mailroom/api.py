"""Client for mailroom's JSON API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from http import HTTPStatus
from typing import Any

import aiohttp
from yarl import URL

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class MailroomError(Exception):
    """Base class for errors talking to mailroom."""


class MailroomConnectionError(MailroomError):
    """Raised when mailroom could not be reached."""


class MailroomResponseError(MailroomError):
    """Raised when the answer is not what mailroom's API promises."""


class DeliveryStatus(StrEnum):
    """Where a parcel is in its journey.

    The values double as entity states and event types, so they are slugs
    rather than the names mailroom itself uses.
    """

    SCHEDULED = "scheduled"
    ON_ITS_WAY = "on_its_way"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    RETURNED = "returned"
    PROBLEM = "problem"
    UNKNOWN = "unknown"


_STATUS_BY_API_NAME = {
    "Scheduled": DeliveryStatus.SCHEDULED,
    "OnItsWay": DeliveryStatus.ON_ITS_WAY,
    "OutForDelivery": DeliveryStatus.OUT_FOR_DELIVERY,
    "Delivered": DeliveryStatus.DELIVERED,
    "Returned": DeliveryStatus.RETURNED,
    "Problem": DeliveryStatus.PROBLEM,
    "Unknown": DeliveryStatus.UNKNOWN,
}


@dataclass(frozen=True)
class Parcel:
    """A parcel as summarised by `/api/parcels`."""

    tracking_number: str
    status: DeliveryStatus
    carrier: str
    description: str | None
    merchant: str | None
    tracking_url: str | None
    expected_arrival: date | None
    overdue: bool
    delivered_at: datetime | None
    last_polled: datetime | None


@dataclass(frozen=True)
class Parcels:
    """The overview mailroom's dashboard shows."""

    # Parcels that have not reached a terminal state.
    current: list[Parcel]
    # Delivered or returned parcels still within mailroom's retention window.
    previous: list[Parcel]


@dataclass(frozen=True)
class Stats:
    """Counts over every record mailroom has on disk."""

    total: int
    delivered: int


def _optional[T](parse: Callable[[str], T], raw: str | None) -> T | None:
    return None if raw is None else parse(raw)


def _parse_parcel(raw: dict[str, Any]) -> Parcel:
    return Parcel(
        tracking_number=raw["tracking_number"],
        status=_STATUS_BY_API_NAME[raw["status"]],
        carrier=raw["carrier"],
        description=raw["description"],
        merchant=raw["merchant"],
        tracking_url=raw["tracking_url"],
        expected_arrival=_optional(date.fromisoformat, raw["expected_arrival"]),
        overdue=raw["overdue"],
        delivered_at=_optional(datetime.fromisoformat, raw["delivered_at"]),
        last_polled=_optional(datetime.fromisoformat, raw["last_polled"]),
    )


def _parse_parcels(raw: dict[str, Any]) -> Parcels:
    return Parcels(
        current=[_parse_parcel(parcel) for parcel in raw["current"]],
        previous=[_parse_parcel(parcel) for parcel in raw["previous"]],
    )


def _parse_stats(raw: dict[str, Any]) -> Stats:
    return Stats(
        total=raw["total"],
        delivered=raw["delivered"],
    )


class MailroomClient:
    """Read-only client for a mailroom instance."""

    def __init__(self, session: aiohttp.ClientSession, url: str) -> None:
        self._session = session
        self._base = URL(url)

    async def parcels(self) -> Parcels:
        """Fetch the parcels the dashboard lists."""
        return await self._get(_parse_parcels, "api", "parcels")

    async def stats(self) -> Stats:
        """Fetch the aggregate statistics."""
        return await self._get(_parse_stats, "api", "stats")

    async def _get[T](self, parse: Callable[[Any], T], *path: str) -> T:
        url = self._base.joinpath(*path)
        try:
            async with self._session.get(url, timeout=REQUEST_TIMEOUT) as response:
                if response.status != HTTPStatus.OK:
                    raise MailroomResponseError(
                        f"{url} returned HTTP {response.status}"
                    )
                body = await response.json()
        except aiohttp.ClientResponseError as err:
            raise MailroomResponseError(f"{url} did not return JSON: {err}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MailroomConnectionError(f"Unable to reach {url}: {err}") from err
        except ValueError as err:
            raise MailroomResponseError(f"{url} returned invalid JSON: {err}") from err
        try:
            return parse(body)
        except (KeyError, TypeError, ValueError) as err:
            raise MailroomResponseError(
                f"{url} returned an unexpected document: {err!r}"
            ) from err
