"""Client for mailroom's JSON API."""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
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


class MailroomAuthError(MailroomError):
    """Raised when whatever guards mailroom does not accept our credentials."""


class MailroomResponseError(MailroomError):
    """Raised when the answer is not what mailroom's API promises."""


class MailroomNotFoundError(MailroomResponseError):
    """Raised when mailroom has nothing at the address asked for."""


class MailroomPreconditionFailedError(MailroomResponseError):
    """Raised when mailroom refuses a request because its condition is not met."""


class MailroomParcelExistsError(MailroomError):
    """Raised when adding a parcel mailroom already has a record for."""


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
class Pickup:
    """Where and until when a parcel can be collected."""

    location: str | None
    code: str | None
    available_from: datetime | None
    available_through: datetime | None


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
    # Set while the parcel is waiting at a locker or parcel shop.
    pickup: Pickup | None


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


@dataclass(frozen=True)
class RefreshResult:
    """What asking the carrier about a parcel came to."""

    # mailroom's own word for it: `updated`, `unchanged`, `no_carrier`,
    # `carrier_not_configured`, `postcode_required` or `no_record`.
    outcome: str
    # The record as it is on disk afterwards.
    parcel: dict[str, Any]


def is_valid_tracking_number(tracking_number: str) -> bool:
    """Whether mailroom accepts this as a tracking number.

    mailroom uses the tracking number as a file name, and only takes ASCII
    letters, digits, `-` and `_`.
    """
    return tracking_number != "" and all(
        char.isascii() and (char.isalnum() or char in "-_") for char in tracking_number
    )


def _optional[T](parse: Callable[[str], T], raw: str | None) -> T | None:
    return None if raw is None else parse(raw)


def _parse_pickup(raw: dict[str, Any] | None) -> Pickup | None:
    if raw is None:
        return None
    return Pickup(
        location=raw["location"],
        code=raw["code"],
        available_from=_optional(datetime.fromisoformat, raw["available_from"]),
        available_through=_optional(datetime.fromisoformat, raw["available_through"]),
    )


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
        # A mailroom from before it reported pickups leaves the key out.
        pickup=_parse_pickup(raw.get("pickup")),
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


@contextmanager
def _missing_parcel(tracking_number: str) -> Generator[None]:
    """Name the parcel that was not found rather than the URL that was asked."""
    try:
        yield
    except MailroomNotFoundError as err:
        raise MailroomNotFoundError(
            f"mailroom has no parcel {tracking_number}"
        ) from err


def _parse_refresh(raw: dict[str, Any]) -> RefreshResult:
    outcome, parcel = raw["outcome"], raw["parcel"]
    if not isinstance(outcome, str) or not isinstance(parcel, dict):
        raise TypeError(f"unexpected refresh result {raw!r}")
    return RefreshResult(outcome=outcome, parcel=parcel)


def _new_parcel(
    tracking_number: str,
    carrier: str | None,
    description: str | None,
    postcode: str | None,
    now: datetime,
) -> dict[str, Any]:
    """Build the record mailroom's own add-a-parcel form would."""
    document: dict[str, Any] = {
        "@type": "ParcelDelivery",
        "trackingNumber": tracking_number,
        "receivedAt": now.isoformat(),
        "deliveryStatus": "OnItsWay",
        "history": [
            {
                "seen_at": now.isoformat(),
                "source": "home-assistant",
                "deliveryStatus": "OnItsWay",
            }
        ],
    }
    if carrier is not None:
        document["provider"] = {"@id": carrier}
    if description is not None:
        document["description"] = description
    if postcode is not None:
        document["deliveryPostalCode"] = postcode
    return document


class MailroomClient:
    """Client for a mailroom instance."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Create a client.

        mailroom has no authentication of its own. `username` and `password`
        are for a reverse proxy in front of it that asks for HTTP basic auth.
        """
        self._session = session
        self._base = URL(url)
        self._headers = (
            {}
            if username is None
            else {"Authorization": aiohttp.encode_basic_auth(username, password or "")}
        )

    async def parcels(self) -> Parcels:
        """Fetch the parcels the dashboard lists."""
        url = self._base.joinpath("api", "parcels")
        return await self._fetch("GET", url, _parse_parcels)

    async def stats(self) -> Stats:
        """Fetch the aggregate statistics."""
        url = self._base.joinpath("api", "stats")
        return await self._fetch("GET", url, _parse_stats)

    async def add_parcel(
        self,
        tracking_number: str,
        *,
        carrier: str | None = None,
        description: str | None = None,
        postcode: str | None = None,
    ) -> None:
        """File a new parcel, on its way.

        `carrier` is the id mailroom knows the carrier by, such as `dhl`.
        Raises MailroomParcelExistsError rather than replace a record.
        """
        url = self._parcel_url(tracking_number)
        exists = MailroomParcelExistsError(
            f"mailroom already has a parcel {tracking_number}"
        )
        # A plain PUT replaces a record wholesale, history included, and a
        # mailroom from before it understood If-None-Match treats this one as
        # plain. Looking first keeps that from costing a record.
        # TODO(jelmer): Drop the look once no such mailroom is around.
        if await self._exists(url):
            raise exists
        document = _new_parcel(
            tracking_number, carrier, description, postcode, datetime.now(UTC)
        )
        try:
            await self._request(
                "PUT", url, json=document, headers={"If-None-Match": "*"}
            )
        except MailroomPreconditionFailedError as err:
            raise exists from err

    async def remove_parcel(self, tracking_number: str) -> None:
        """Delete a parcel's record. Raises MailroomNotFoundError if absent."""
        url = self._parcel_url(tracking_number)
        with _missing_parcel(tracking_number):
            await self._request("DELETE", url)

    async def refresh_parcel(self, tracking_number: str) -> RefreshResult:
        """Have mailroom ask the carrier about a parcel now.

        Raises MailroomNotFoundError if mailroom has no such parcel.
        """
        url = self._parcel_url(tracking_number) / "refresh"
        with _missing_parcel(tracking_number):
            return await self._fetch("POST", url, _parse_refresh)

    def _parcel_url(self, tracking_number: str) -> URL:
        # Anything else could name a different endpoint, e.g. `..`.
        if not is_valid_tracking_number(tracking_number):
            raise ValueError(f"invalid tracking number {tracking_number!r}")
        return self._base.joinpath("api", "parcel", tracking_number)

    async def _exists(self, url: URL) -> bool:
        try:
            await self._request("GET", url)
        except MailroomNotFoundError:
            return False
        return True

    async def _fetch[T](self, method: str, url: URL, parse: Callable[[Any], T]) -> T:
        body = await self._request(method, url)
        try:
            return parse(body)
        except (KeyError, TypeError, ValueError) as err:
            raise MailroomResponseError(
                f"{url} returned an unexpected document: {err!r}"
            ) from err

    async def _request(
        self,
        method: str,
        url: URL,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Return the decoded body, or None where mailroom sends none."""
        try:
            async with self._session.request(
                method,
                url,
                json=json,
                headers={**self._headers, **(headers or {})},
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                    raise MailroomAuthError(
                        f"{url} refused the credentials (HTTP {response.status})"
                    )
                if response.status == HTTPStatus.NOT_FOUND:
                    raise MailroomNotFoundError(f"{url} was not found")
                if response.status == HTTPStatus.PRECONDITION_FAILED:
                    raise MailroomPreconditionFailedError(
                        f"{url} did not meet the request's condition"
                    )
                if response.status == HTTPStatus.NO_CONTENT:
                    return None
                if response.status not in (HTTPStatus.OK, HTTPStatus.CREATED):
                    raise MailroomResponseError(
                        f"{url} returned HTTP {response.status}"
                    )
                return await response.json()
        except aiohttp.ClientResponseError as err:
            raise MailroomResponseError(f"{url} did not return JSON: {err}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MailroomConnectionError(f"Unable to reach {url}: {err}") from err
        except ValueError as err:
            raise MailroomResponseError(f"{url} returned invalid JSON: {err}") from err
