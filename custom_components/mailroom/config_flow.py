"""Config flow for the mailroom integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from yarl import URL

from .api import (
    MailroomAuthError,
    MailroomClient,
    MailroomConnectionError,
    MailroomResponseError,
)
from .const import DOMAIN

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
URL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Optional(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)
CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)


def normalise_url(raw: str) -> str:
    """Return the canonical form of a mailroom base URL.

    Raises ValueError for anything that is not a plain http(s) URL.
    """
    url = URL(raw.strip())
    if url.scheme not in ("http", "https") or not url.host:
        raise ValueError(f"not an http(s) URL: {raw!r}")
    if url.query_string or url.fragment:
        raise ValueError(f"URL carries a query or fragment: {raw!r}")
    # They would end up in the link to the dashboard shown for the device.
    if url.user or url.password:
        raise ValueError("URL carries credentials")
    return str(url.with_path(url.path.rstrip("/")))


def credentials(user_input: Mapping[str, Any]) -> dict[str, str]:
    """Pick the credentials out of a submitted form, if any were given.

    Raises ValueError for a password without a username.
    """
    username = user_input.get(CONF_USERNAME, "")
    password = user_input.get(CONF_PASSWORD, "")
    if not username:
        if password:
            raise ValueError("a password needs a username to go with it")
        return {}
    return {CONF_USERNAME: username, CONF_PASSWORD: password}


class MailroomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for mailroom."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the address of the mailroom dashboard."""
        return await self._async_step_url("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Point an existing entry at another address."""
        return await self._async_step_url("reconfigure", user_input)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start over with the credentials after they were refused."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for credentials the proxy in front of mailroom accepts."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {CONF_URL: entry.data[CONF_URL], **credentials(user_input)}
            if (error := await self._async_check(data)) is None:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA,
                user_input or {CONF_USERNAME: entry.data.get(CONF_USERNAME)},
            ),
            errors=errors,
            description_placeholders={"url": entry.data[CONF_URL]},
        )

    async def _async_step_url(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reconfiguring = self.source == SOURCE_RECONFIGURE

        if user_input is not None:
            data: dict[str, str] = {}
            try:
                data[CONF_URL] = normalise_url(user_input[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            try:
                data.update(credentials(user_input))
            except ValueError:
                errors[CONF_USERNAME] = "username_required"

            if not errors:
                self._async_abort_entries_match({CONF_URL: data[CONF_URL]})
                if (error := await self._async_check(data)) is not None:
                    errors["base"] = error
                elif reconfiguring:
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(), data=data
                    )
                else:
                    return self.async_create_entry(title="Mailroom", data=data)
        elif reconfiguring:
            user_input = dict(self._get_reconfigure_entry().data)

        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(URL_SCHEMA, user_input),
            errors=errors,
            description_placeholders={"example_url": "http://localhost:8080"},
        )

    async def _async_check(self, data: Mapping[str, str]) -> str | None:
        """Try to reach mailroom, returning the error to show if that fails."""
        client = MailroomClient(
            async_get_clientsession(self.hass),
            data[CONF_URL],
            data.get(CONF_USERNAME),
            data.get(CONF_PASSWORD),
        )
        try:
            await client.stats()
        except MailroomAuthError:
            return "invalid_auth"
        except MailroomConnectionError:
            return "cannot_connect"
        except MailroomResponseError:
            return "invalid_response"
        return None
