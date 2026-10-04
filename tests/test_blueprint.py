"""Tests for the automation blueprint shipped with the integration."""

from __future__ import annotations

import pathlib

import pytest
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint import Blueprint
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.template import Template
from homeassistant.util.yaml import Input, load_yaml_dict

PATH = (
    pathlib.Path(__file__).parent.parent
    / "blueprints/automation/mailroom/parcel_notification.yaml"
)


def test_parcel_notification_is_a_valid_automation_blueprint() -> None:
    blueprint = Blueprint(
        load_yaml_dict(str(PATH)),
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )

    assert blueprint.name == "Mailroom parcel notification"
    assert set(blueprint.inputs) == {"parcel_event", "statuses", "notify_device"}


@pytest.mark.parametrize(
    ("description", "title"),
    [("Bicycle bell", "Bicycle bell"), (None, "TQ1")],
)
async def test_parcel_notification_wording(
    hass: HomeAssistant, description: str | None, title: str
) -> None:
    document = load_yaml_dict(str(PATH))
    [action] = document["actions"]
    state = State(
        "event.mailroom_parcel_update",
        "2026-10-04T12:00:00.000+00:00",
        {
            "event_type": "out_for_delivery",
            "tracking_number": "TQ1",
            "carrier": "Royal Mail",
            "description": description,
        },
    )
    variables = {"trigger": {"to_state": state}}
    for name, value in document["variables"].items():
        if isinstance(value, Input):
            continue
        variables[name] = (
            Template(value, hass).async_render(variables)
            if isinstance(value, str)
            else value
        )

    assert variables["status"] == "out_for_delivery"
    assert Template(action["title"], hass).async_render(variables) == title
    assert (
        Template(action["message"], hass).async_render(variables)
        == "Your parcel with Royal Mail is out for delivery."
    )
