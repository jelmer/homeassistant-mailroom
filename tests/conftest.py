"""Fixtures for the mailroom integration tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Generator

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.mailroom.const import DOMAIN, UPDATE_INTERVAL

from . import BASE_URL, mock_api


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Let Home Assistant load `custom_components` during a test."""
    yield


@pytest.fixture
async def config_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> MockConfigEntry:
    """A mailroom entry, set up against the canned documents."""
    mock_api(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, title="Mailroom", data={CONF_URL: BASE_URL})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def tick(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> Callable[[], Awaitable[None]]:
    """Run the next scheduled poll."""

    async def _tick() -> None:
        freezer.tick(UPDATE_INTERVAL)
        async_fire_time_changed(hass)
        # The coordinator refreshes in a background task.
        await hass.async_block_till_done(wait_background_tasks=True)

    return _tick
