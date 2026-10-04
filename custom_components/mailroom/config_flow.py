"""Config flow for the mailroom integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from yarl import URL

from .api import MailroomClient, MailroomConnectionError, MailroomResponseError
from .const import DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema({vol.Required(CONF_URL): str})


def normalise_url(raw: str) -> str:
    """Return the canonical form of a mailroom base URL.

    Raises ValueError for anything that is not a plain http(s) URL.
    """
    url = URL(raw.strip())
    if url.scheme not in ("http", "https") or not url.host:
        raise ValueError(f"not an http(s) URL: {raw!r}")
    if url.query_string or url.fragment:
        raise ValueError(f"URL carries a query or fragment: {raw!r}")
    return str(url.with_path(url.path.rstrip("/")))


class MailroomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for mailroom."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the address of the mailroom dashboard."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                url = normalise_url(user_input[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            else:
                self._async_abort_entries_match({CONF_URL: url})
                client = MailroomClient(async_get_clientsession(self.hass), url)
                try:
                    await client.stats()
                except MailroomConnectionError:
                    errors["base"] = "cannot_connect"
                except MailroomResponseError:
                    errors["base"] = "invalid_response"
                else:
                    return self.async_create_entry(
                        title="Mailroom", data={CONF_URL: url}
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
            description_placeholders={"example_url": "http://localhost:8080"},
        )
