// Dashboard card listing the parcels of a mailroom sensor.
//
// Any of the integration's sensors with a `parcels` attribute will do as
// `entity`. Everything shown comes from mail and carrier APIs, so it only
// ever reaches the page as text, never as markup.

const STATUSES = {
  scheduled: { label: "Scheduled", icon: "mdi:calendar-clock" },
  on_its_way: { label: "On its way", icon: "mdi:truck-fast" },
  out_for_delivery: { label: "Out for delivery", icon: "mdi:truck-delivery" },
  delivered: { label: "Delivered", icon: "mdi:package-variant-closed-check" },
  returned: { label: "Returned", icon: "mdi:keyboard-return" },
  problem: { label: "Problem", icon: "mdi:alert-circle-outline" },
  unknown: { label: "Unknown", icon: "mdi:help-circle-outline" },
};

const FIELD_LABELS = {
  entity: "Parcels to list",
  title: "Title",
  delivered_entity: "Second list, e.g. recently delivered",
  max_items: "Most parcels to show per list",
};

const PARCEL_SENSORS = { filter: { integration: "mailroom", domain: "sensor" } };

const STYLE = `
  .list + .list {
    margin-top: 16px;
  }
  .heading {
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 12px);
    font-weight: 500;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
    text-transform: uppercase;
  }
  .parcel {
    align-items: center;
    color: inherit;
    display: flex;
    gap: 12px;
    padding: 8px 0;
    text-decoration: none;
  }
  a.parcel:hover .primary {
    text-decoration: underline;
  }
  ha-icon {
    color: var(--state-icon-color);
    flex: none;
  }
  .parcel.out_for_delivery ha-icon,
  .parcel.delivered ha-icon {
    color: var(--success-color);
  }
  .parcel.problem ha-icon {
    color: var(--error-color);
  }
  .main {
    flex: 1;
    min-width: 0;
  }
  .primary,
  .secondary {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .secondary,
  .side,
  .more,
  .empty {
    color: var(--secondary-text-color);
    font-size: var(--ha-font-size-s, 12px);
  }
  .pickup {
    font-size: var(--ha-font-size-s, 12px);
  }
  .pickup .code {
    font-family: var(--ha-font-family-code, monospace);
    font-weight: 500;
  }
  .side {
    flex: none;
    text-align: right;
  }
  .side .status {
    color: var(--primary-text-color);
  }
  .side .late {
    color: var(--warning-color);
  }
  .warning {
    color: var(--error-color);
  }
`;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

// `2026-10-04` as midnight local time. `new Date("2026-10-04")` would be
// midnight UTC, which is the day before in the Americas.
function localDate(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function daysFromToday(date) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const day = new Date(date);
  day.setHours(0, 0, 0, 0);
  return Math.round((day - today) / 86400000);
}

class MailroomParcelsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) =>
        id.startsWith("sensor.") &&
        id.endsWith("_in_transit") &&
        Array.isArray(hass.states[id].attributes.parcels),
    );
    return { entity: entity ?? "" };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: PARCEL_SENSORS } },
        { name: "title", selector: { text: {} } },
        { name: "delivered_entity", selector: { entity: PARCEL_SENSORS } },
        { name: "max_items", selector: { number: { min: 1, mode: "box" } } },
      ],
      computeLabel: (field) => FIELD_LABELS[field.name],
    };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("entity is required");
    }
    if (
      config.max_items !== undefined &&
      !(Number.isInteger(config.max_items) && config.max_items > 0)
    ) {
      throw new Error("max_items must be a whole number above zero");
    }
    this._config = config;
    this._shown = undefined;
    if (this._hass) {
      this.hass = this._hass;
    }
  }

  set hass(hass) {
    this._hass = hass;
    const states = this._entities().map((id) => hass.states[id]);
    const unchanged =
      this._shown !== undefined &&
      this._language === hass.locale?.language &&
      states.every((state, index) => state === this._shown[index]);
    if (unchanged) {
      return;
    }
    this._shown = states;
    this._language = hass.locale?.language;
    this._render();
  }

  getCardSize() {
    const parcels = (this._shown ?? []).reduce(
      (count, state) => count + this._visible(state).length,
      0,
    );
    return 1 + Math.max(1, parcels);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, min_rows: 2 };
  }

  _entities() {
    const { entity, delivered_entity: delivered } = this._config;
    return delivered ? [entity, delivered] : [entity];
  }

  _parcels(state) {
    const parcels = state?.attributes.parcels;
    return Array.isArray(parcels) ? parcels : undefined;
  }

  _visible(state) {
    const parcels = this._parcels(state) ?? [];
    return parcels.slice(0, this._config.max_items ?? parcels.length);
  }

  _render() {
    const entities = this._entities();
    const first = this._shown[0];
    const card = element("ha-card");
    card.header =
      this._config.title ?? first?.attributes.friendly_name ?? "Parcels";
    const content = element("div", "card-content");
    entities.forEach((id, index) => {
      // With one list the card's own title says what it is.
      const heading = entities.length > 1 && index > 0;
      content.append(this._list(id, this._shown[index], heading));
    });
    card.append(content);
    const style = element("style", undefined, STYLE);
    this.shadowRoot.replaceChildren(style, card);
  }

  _list(id, state, withHeading) {
    const list = element("div", "list");
    if (state === undefined) {
      list.append(element("div", "warning", `Entity not found: ${id}`));
      return list;
    }
    if (withHeading) {
      list.append(element("div", "heading", state.attributes.friendly_name ?? id));
    }
    const parcels = this._parcels(state);
    if (parcels === undefined) {
      const reason =
        state.state === "unavailable"
          ? `${id} is unavailable`
          : `${id} does not list parcels`;
      list.append(element("div", "warning", reason));
      return list;
    }
    if (parcels.length === 0) {
      list.append(element("div", "empty", "No parcels"));
      return list;
    }
    const visible = this._visible(state);
    for (const parcel of visible) {
      list.append(this._parcel(parcel));
    }
    if (visible.length < parcels.length) {
      const hidden = parcels.length - visible.length;
      list.append(element("div", "more", `and ${hidden} more`));
    }
    return list;
  }

  _parcel(parcel) {
    const status = STATUSES[parcel.status] ?? STATUSES.unknown;
    const row = element(parcel.tracking_url ? "a" : "div", `parcel ${parcel.status}`);
    if (parcel.tracking_url) {
      row.href = parcel.tracking_url;
      row.target = "_blank";
      row.rel = "noopener noreferrer";
    }

    const icon = element("ha-icon");
    icon.icon = status.icon;
    row.append(icon);

    const main = element("div", "main");
    main.append(
      element("div", "primary", parcel.description ?? parcel.tracking_number),
    );
    const details = [parcel.carrier, parcel.merchant];
    if (parcel.description) {
      details.push(parcel.tracking_number);
    }
    main.append(element("div", "secondary", details.filter(Boolean).join(" · ")));
    if (parcel.pickup) {
      main.append(this._pickup(parcel.pickup));
    }
    row.append(main);

    const side = element("div", "side");
    side.append(element("div", "status", status.label));
    const when = this._when(parcel);
    if (when) {
      side.append(element("div", parcel.overdue ? "late" : "when", when));
    }
    row.append(side);
    return row;
  }

  _pickup(pickup) {
    const line = element("div", "pickup");
    line.append(pickup.location ? `Collect at ${pickup.location}` : "Ready to collect");
    if (pickup.code) {
      line.append(", code ", element("span", "code", pickup.code));
    }
    if (pickup.available_through) {
      line.append(`, by ${this._day(new Date(pickup.available_through))}`);
    }
    return line;
  }

  _when(parcel) {
    if (parcel.delivered_at) {
      return this._day(new Date(parcel.delivered_at));
    }
    if (!parcel.expected_arrival) {
      return undefined;
    }
    const day = this._day(localDate(parcel.expected_arrival));
    return parcel.overdue ? `Was due ${day}` : `Due ${day}`;
  }

  // "today", "tomorrow" and "yesterday" where they apply, else "Mon 6 Oct".
  _day(date) {
    const language = this._language ?? navigator.language;
    const days = daysFromToday(date);
    if (Math.abs(days) <= 1) {
      return new Intl.RelativeTimeFormat(language, { numeric: "auto" }).format(
        days,
        "day",
      );
    }
    return new Intl.DateTimeFormat(language, {
      weekday: "short",
      day: "numeric",
      month: "short",
    }).format(date);
  }
}

// The frontend may be told about this file twice, by the integration and
// by a dashboard resource someone added by hand.
if (!customElements.get("mailroom-parcels-card")) {
  customElements.define("mailroom-parcels-card", MailroomParcelsCard);
  window.customCards = window.customCards ?? [];
  window.customCards.push({
    type: "mailroom-parcels-card",
    name: "Mailroom parcels",
    description: "The parcels a mailroom sensor counts, with status and dates.",
    preview: true,
    documentationURL: "https://github.com/jelmer/homeassistant-mailroom#dashboard-card",
  });
}
