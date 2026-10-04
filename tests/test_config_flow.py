"""Tests for the mailroom config flow."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
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
        "http://someone:secret@mailroom.test",
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


async def test_reconfigure_points_the_entry_at_another_address(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    new_url = "http://mailroom.test/mailroom"
    mock_api(aioclient_mock, base_url=new_url)

    result = await config_entry.start_reconfigure_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    schema = result["data_schema"]
    assert schema is not None
    assert {str(field): field.description for field in schema.schema} == {
        "url": {"suggested_value": BASE_URL},
        "username": None,
        "password": None,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: f"{new_url}/"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data == {CONF_URL: new_url}
    assert config_entry.state is ConfigEntryState.LOADED


async def test_reconfigure_keeps_the_entry_when_the_new_address_fails(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.get("http://elsewhere.test/api/stats", status=404)

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "http://elsewhere.test"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "invalid_response"}
    assert config_entry.data == {CONF_URL: BASE_URL}


async def test_reconfigure_accepts_the_address_it_already_has(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: BASE_URL}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_reconfigure_refuses_the_address_of_another_entry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    other_url = "http://other.test"
    other = MockConfigEntry(domain=DOMAIN, title="Mailroom", data={CONF_URL: other_url})
    other.add_to_hass(hass)

    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: other_url}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data == {CONF_URL: BASE_URL}


async def test_credentials_are_kept_with_the_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: BASE_URL, CONF_USERNAME: "someone", CONF_PASSWORD: "secret"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_URL: BASE_URL,
        CONF_USERNAME: "someone",
        CONF_PASSWORD: "secret",
    }


@pytest.mark.parametrize("status", [401, 403])
async def test_refused_credentials_can_be_corrected(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, status: int
) -> None:
    aioclient_mock.get(f"{BASE_URL}/api/stats", status=status)

    result = await _submit(hass, BASE_URL)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: BASE_URL, CONF_USERNAME: "someone"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_URL: BASE_URL,
        CONF_USERNAME: "someone",
        CONF_PASSWORD: "",
    }


async def test_a_password_needs_a_username(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: BASE_URL, CONF_PASSWORD: "secret"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_USERNAME: "username_required"}
    assert aioclient_mock.mock_calls == []


async def test_reconfigure_can_drop_the_credentials(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_api(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Mailroom",
        data={CONF_URL: BASE_URL, CONF_USERNAME: "someone", CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: BASE_URL}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_URL: BASE_URL}


async def test_refused_credentials_while_running_ask_for_new_ones(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    tick: Callable[[], Awaitable[None]],
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE_URL}/api/parcels", status=401)
    aioclient_mock.get(f"{BASE_URL}/api/stats", status=401)
    await tick()

    [flow] = hass.config_entries.flow.async_progress()
    assert flow["context"]["source"] == config_entries.SOURCE_REAUTH
    assert flow["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_USERNAME: "someone", CONF_PASSWORD: "wrong"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_USERNAME: "someone", CONF_PASSWORD: "secret"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data == {
        CONF_URL: BASE_URL,
        CONF_USERNAME: "someone",
        CONF_PASSWORD: "secret",
    }
    assert config_entry.state is ConfigEntryState.LOADED
