"""Tests for the mailroom API client."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.mailroom.api import (
    DeliveryStatus,
    MailroomClient,
    MailroomConnectionError,
    MailroomNotFoundError,
    MailroomResponseError,
    Parcel,
    Parcels,
    RefreshResult,
    Stats,
)

from . import BASE_URL, STATS, mock_api, parcel_json


@pytest.fixture
async def client(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> MailroomClient:
    # Depends on the mocker so the session is created after it is in place.
    return MailroomClient(async_get_clientsession(hass), BASE_URL)


async def test_parcels(
    client: MailroomClient, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock)

    assert await client.parcels() == Parcels(
        current=[
            Parcel(
                tracking_number="JD2",
                status=DeliveryStatus.ON_ITS_WAY,
                carrier="dhl",
                description=None,
                merchant=None,
                tracking_url="https://www.dhl.com/en/express/tracking.html?AWB=JD2",
                expected_arrival=date(2026, 10, 3),
                overdue=True,
                delivered_at=None,
                last_polled=None,
            ),
            Parcel(
                tracking_number="TQ1",
                status=DeliveryStatus.OUT_FOR_DELIVERY,
                carrier="Royal Mail",
                description="Bicycle bell",
                merchant="Bell Shop",
                tracking_url=None,
                expected_arrival=date(2026, 10, 4),
                overdue=False,
                delivered_at=None,
                last_polled=None,
            ),
        ],
        previous=[
            Parcel(
                tracking_number="3S3",
                status=DeliveryStatus.DELIVERED,
                carrier="PostNL",
                description="Stroopwafels",
                merchant=None,
                tracking_url=None,
                expected_arrival=None,
                overdue=False,
                delivered_at=datetime(2026, 10, 4, 14, 28, 56, tzinfo=UTC),
                # chrono writes nanoseconds; anything past microseconds is cut.
                last_polled=datetime(2026, 10, 4, 14, 28, 56, 123456, tzinfo=UTC),
            ),
        ],
    )


async def test_stats(
    client: MailroomClient, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock)

    assert await client.stats() == Stats(total=40, delivered=37)


@pytest.mark.parametrize(
    "base_url", ["http://mailroom.test/mailroom", "http://mailroom.test/mailroom/"]
)
async def test_base_path_is_kept(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, base_url: str
) -> None:
    mock_api(aioclient_mock, base_url="http://mailroom.test/mailroom")
    client = MailroomClient(async_get_clientsession(hass), base_url)

    assert await client.stats() == Stats(total=40, delivered=37)


@pytest.mark.parametrize(
    ("api_name", "status"),
    [
        ("Scheduled", DeliveryStatus.SCHEDULED),
        ("OnItsWay", DeliveryStatus.ON_ITS_WAY),
        ("OutForDelivery", DeliveryStatus.OUT_FOR_DELIVERY),
        ("Delivered", DeliveryStatus.DELIVERED),
        ("Returned", DeliveryStatus.RETURNED),
        ("Problem", DeliveryStatus.PROBLEM),
        ("Unknown", DeliveryStatus.UNKNOWN),
    ],
)
async def test_every_status_mailroom_emits_is_understood(
    client: MailroomClient,
    aioclient_mock: AiohttpClientMocker,
    api_name: str,
    status: DeliveryStatus,
) -> None:
    mock_api(aioclient_mock, {"current": [parcel_json("A1", api_name)], "previous": []})

    parcels = await client.parcels()

    assert [parcel.status for parcel in parcels.current] == [status]


@pytest.mark.parametrize(
    "document",
    [
        # A status this integration has never heard of.
        {"current": [parcel_json("A1", "Teleported")], "previous": []},
        # A parcel missing a field.
        {"current": [{"tracking_number": "A1", "status": "Delivered"}], "previous": []},
        {"current": [parcel_json("A1", "Delivered", expected_arrival="soon")]},
        {"current": []},
        ["not", "an", "object"],
    ],
)
async def test_an_unexpected_document_is_an_error(
    client: MailroomClient, aioclient_mock: AiohttpClientMocker, document: Any
) -> None:
    mock_api(aioclient_mock, document)

    with pytest.raises(MailroomResponseError):
        await client.parcels()


async def test_an_http_error_is_an_error(
    client: MailroomClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/stats", status=500, json=STATS)

    with pytest.raises(MailroomResponseError, match="HTTP 500"):
        await client.stats()


async def test_a_body_that_is_not_json_is_an_error(
    client: MailroomClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/stats", text="<html>hello</html>")

    with pytest.raises(MailroomResponseError):
        await client.stats()


@pytest.mark.parametrize(
    "error", [aiohttp.ClientConnectionError("refused"), TimeoutError()]
)
async def test_failing_to_connect_is_a_connection_error(
    client: MailroomClient, aioclient_mock: AiohttpClientMocker, error: Exception
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/parcels", exc=error)

    with pytest.raises(MailroomConnectionError):
        await client.parcels()


@pytest.mark.parametrize(
    "tracking_number", ["", "..", "TQ1/refresh", "TQ 1", "TQ\u00e9"]
)
async def test_an_invalid_tracking_number_is_refused_before_any_request(
    client: MailroomClient, aioclient_mock: AiohttpClientMocker, tracking_number: str
) -> None:
    with pytest.raises(ValueError):
        await client.add_parcel(tracking_number)
    with pytest.raises(ValueError):
        await client.remove_parcel(tracking_number)
    with pytest.raises(ValueError):
        await client.refresh_parcel(tracking_number)

    assert aioclient_mock.mock_calls == []


async def test_refresh_parcel(
    client: MailroomClient, aioclient_mock: AiohttpClientMocker
) -> None:
    record = {"trackingNumber": "TQ-1_a", "deliveryStatus": "Delivered"}
    aioclient_mock.post(
        f"{BASE_URL}/api/parcel/TQ-1_a/refresh",
        json={"outcome": "unchanged", "parcel": record},
    )

    assert await client.refresh_parcel("TQ-1_a") == RefreshResult(
        outcome="unchanged", parcel=record
    )


@pytest.mark.parametrize(
    "document", [{"outcome": "updated"}, {"outcome": 1, "parcel": {}}, []]
)
async def test_an_unexpected_refresh_result_is_an_error(
    client: MailroomClient, aioclient_mock: AiohttpClientMocker, document: Any
) -> None:
    aioclient_mock.post(f"{BASE_URL}/api/parcel/TQ1/refresh", json=document)

    with pytest.raises(MailroomResponseError):
        await client.refresh_parcel("TQ1")


async def test_removing_a_parcel_mailroom_does_not_have(
    client: MailroomClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.delete(f"{BASE_URL}/api/parcel/TQ1", status=404)

    with pytest.raises(MailroomNotFoundError):
        await client.remove_parcel("TQ1")


async def test_adding_a_parcel_mailroom_refuses(
    client: MailroomClient, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/parcel/TQ1", status=404)
    aioclient_mock.put(f"{BASE_URL}/api/parcel/TQ1", status=400)

    with pytest.raises(MailroomResponseError, match="HTTP 400"):
        await client.add_parcel("TQ1")
