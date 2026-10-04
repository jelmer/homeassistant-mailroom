# Mailroom for Home Assistant

A [Home Assistant](https://www.home-assistant.io/) custom integration for
[mailroom](https://github.com/jelmer/mailroom), the parcel dashboard and
carrier-tracking poller built on top of
[mailsift](https://github.com/jelmer/mailsift).

It reads mailroom's JSON API every five minutes and exposes what the
dashboard shows as sensors, plus an event entity that fires when a parcel
changes status. Actions add, refresh and remove parcels.

## Entities

| Entity | What |
| --- | --- |
| In transit | Parcels that have not been delivered or returned |
| Out for delivery | Parcels in transit that are out for delivery |
| Arriving today | Parcels in transit whose expected arrival date is today |
| Overdue | Parcels in transit whose expected arrival date has passed |
| Problem | Parcels in transit that the carrier reports a problem with |
| Delivered | Delivered parcels, over every record mailroom has |
| Total parcels | Every record mailroom has |
| Parcel update | Event entity; fires when a parcel appears or changes status |

The first five sensors list the parcels they count in a `parcels`
attribute, each with its tracking number, status, carrier, description,
merchant, tracking URL and expected arrival date. That attribute is kept
out of the recorder.

"In transit" counts the same parcels as the dashboard does, so it includes
ones mailroom has given up on and shows as `Unknown`.

The statuses are mailroom's own: `scheduled`, `on_its_way`,
`out_for_delivery`, `delivered`, `returned`, `problem` and `unknown`.

### Parcel updates

The event type of `event.mailroom_parcel_update` is the status the parcel
moved to. The parcel's details are attributes of the event, along with
`previous_status`, which is empty for a parcel that was not there before.

Parcels that are already there when the integration is first set up do not
fire. The status last reported for each parcel is stored, so a change that
happens while Home Assistant is not running fires on the first poll after
it has started, which can be up to five minutes later.

    automation:
      - alias: Announce parcels that are out for delivery
        triggers:
          - trigger: state
            entity_id: event.mailroom_parcel_update
            not_from: unavailable
        conditions:
          - condition: state
            entity_id: event.mailroom_parcel_update
            attribute: event_type
            state: out_for_delivery
        actions:
          - action: notify.notify
            data:
              message: >-
                {{ trigger.to_state.attributes.description
                   or trigger.to_state.attributes.tracking_number }}
                is out for delivery with
                {{ trigger.to_state.attributes.carrier }}.

## Actions

| Action | What |
| --- | --- |
| `mailroom.add_parcel` | File a new parcel, on its way |
| `mailroom.refresh_parcel` | Have mailroom poll the carrier for a parcel now |
| `mailroom.remove_parcel` | Delete a parcel's record, history included |

All three take a `tracking_number`, and a `config_entry_id` that is only
needed when more than one mailroom is set up.

`add_parcel` also takes an optional `carrier`, `description` and
`postcode`. The carrier is the id mailroom knows it by, such as `dhl`,
`dpd`, `postnl`, `royal-mail` or `ups`; a parcel without one is not polled.
DPD and PostNL need the postcode to look a parcel up. Adding a tracking
number mailroom already has is refused rather than replacing the record.

`refresh_parcel` returns mailroom's `outcome` (`updated`, `unchanged`,
`no_record`, `no_carrier`, `carrier_not_configured` or `postcode_required`)
and the parcel's record as it is afterwards:

    actions:
      - action: mailroom.refresh_parcel
        data:
          tracking_number: JD014600006281234567
        response_variable: refreshed

## Installation

### HACS

1. Add this repository as a custom repository in HACS, with the category
   "Integration"
2. Install "Mailroom"
3. Restart Home Assistant

### Manual

Copy the `custom_components/mailroom` directory into the
`custom_components` directory of your Home Assistant configuration and
restart Home Assistant.

## Configuration

Go to Settings > Devices & Services > Add Integration, search for
"Mailroom" and enter the URL of the dashboard, e.g. `http://localhost:8080`.
Include the base path if mailroom is mounted under one. If mailroom moves,
"Reconfigure" on the integration's entry changes the URL in place.

Home Assistant has to be able to reach mailroom over HTTP, so a mailroom
that only listens on a unix socket needs a reverse proxy in front of it.
mailroom has no authentication of its own; if the proxy adds any, this
integration cannot get past it at the moment.

The diagnostics download for the entry holds what the last poll fetched,
with tracking numbers, tracking URLs, descriptions and merchants redacted.

## Development

    uv venv
    uv pip install --group dev
    .venv/bin/pytest

## Licence

Apache-2.0.
