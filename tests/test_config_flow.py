"""Tests for the mailroom config flow."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.mailroom.config_flow import normalise_url
from custom_components.mailroom.const import DOMAIN

from . import BASE_URL, mock_api


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://mailroom.test:8080", "http://mailroom.test:8080"),
        ("http://mailroom.test:8080/", "http://mailroom.test:8080"),
        ("  https://example.com/mailroom/ ", "https://example.com/mailroom"),
    ],
)
def test_normalise_url(raw: str, expected: str) -> None:
    assert normalise_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "mailroom.test:8080",
        "unix:/run/mailroom.sock",
        "ftp://mailroom.test",
        "http://mailroom.test/?q=bell",
        "http://mailroom.test/#transit",
    ],
)
def test_normalise_url_rejects_what_is_not_a_base_url(raw: str) -> None:
    with pytest.raises(ValueError):
        normalise_url(raw)


async def _submit(hass: HomeAssistant, url: str) -> config_entries.ConfigFlowResult:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: url}
    )


async def test_a_reachable_mailroom_creates_an_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock)

    result = await _submit(hass, f"{BASE_URL}/")

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Mailroom"
    assert result["data"] == {CONF_URL: BASE_URL}


async def test_an_invalid_url_is_reported_on_the_field(hass: HomeAssistant) -> None:
    result = await _submit(hass, "mailroom.test:8080")

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_URL: "invalid_url"}


async def test_an_unreachable_mailroom_can_be_retried(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{BASE_URL}/api/stats", exc=aiohttp.ClientConnectionError("refused")
    )

    result = await _submit(hass, BASE_URL)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: BASE_URL}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_something_other_than_mailroom_is_refused(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/stats", status=404)

    result = await _submit(hass, BASE_URL)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_response"}


async def test_the_same_mailroom_is_not_added_twice(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    result = await _submit(hass, f"{BASE_URL}/")

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
