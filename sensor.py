"""Sensor platform for the Met Éireann Irish Sea Buoy integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_BUOY_ID,
    DEFAULT_BUOY_ID,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SENSOR_METADATA,
)
from .coordinator import MetIeBuoyCoordinator

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# YAML platform schema
# ---------------------------------------------------------------------------
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_BUOY_ID, default=DEFAULT_BUOY_ID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
    }
)

# Columns to skip — these are metadata / timestamps, not measurements.
# The "time" column is exposed as an attribute on every sensor instead.
_SKIP_COLUMNS = {"time", "date", "datetime", "timestamp", "station", "buoy"}


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Met.ie buoy sensors from configuration.yaml."""
    buoy_id: str = config[CONF_BUOY_ID]
    platform_name: str = config[CONF_NAME]
    scan_interval: int = config[CONF_SCAN_INTERVAL]

    coordinator = MetIeBuoyCoordinator(hass, buoy_id, scan_interval)

    # Do the first refresh now so we know which columns exist.
    await coordinator.async_refresh()

    if coordinator.last_exception:
        _LOGGER.error(
            "Initial fetch for buoy %s failed: %s", buoy_id, coordinator.last_exception
        )
        return

    data: dict[str, str] = coordinator.data

    entities: list[MetIeBuoySensor] = []
    for column in data:
        if column.lower() in _SKIP_COLUMNS:
            continue
        entities.append(
            MetIeBuoySensor(
                coordinator=coordinator,
                column=column,
                platform_name=platform_name,
                buoy_id=buoy_id,
            )
        )

    if not entities:
        _LOGGER.warning("No sensor columns discovered for buoy %s", buoy_id)
        return

    async_add_entities(entities, update_before_add=False)
    _LOGGER.info(
        "Met.ie buoy %s: added %d sensors (%s)",
        buoy_id,
        len(entities),
        ", ".join(e.name for e in entities),
    )


# ---------------------------------------------------------------------------
# Sensor entity
# ---------------------------------------------------------------------------

class MetIeBuoySensor(CoordinatorEntity[MetIeBuoyCoordinator], SensorEntity):
    """A single measurement from a Met.ie buoy CSV column."""

    _attr_has_entity_name = False
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: MetIeBuoyCoordinator,
        column: str,
        platform_name: str,
        buoy_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._column = column
        self._buoy_id = buoy_id

        # Look up curated metadata, fall back to sensible defaults.
        meta = SENSOR_METADATA.get(column)
        if meta:
            friendly, unit, device_class, icon = meta
            self._attr_name = f"{platform_name} {friendly}"
            self._attr_native_unit_of_measurement = unit
            self._attr_icon = icon
            if device_class:
                try:
                    self._attr_device_class = SensorDeviceClass(device_class)
                except ValueError:
                    self._attr_device_class = None
        else:
            # Unknown column — use the column name as-is.
            self._attr_name = f"{platform_name} {column}"
            self._attr_native_unit_of_measurement = None
            self._attr_device_class = None
            self._attr_icon = "mdi:chart-line"

        # Unique ID: domain + buoy_id + column name (lower, no spaces)
        self._attr_unique_id = f"{DOMAIN}_{buoy_id}_{column.lower().replace(' ', '_')}"

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> float | str | None:
        """Return the sensor value, coerced to float where possible."""
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self._column)
        if raw is None or raw.strip() in ("", "NaN", "N/A", "null", "NULL"):
            return None
        try:
            return float(raw)
        except ValueError:
            return raw

    # ------------------------------------------------------------------
    # Extra attributes — attach the timestamp and all other fields so the
    # user can see the full row in Developer Tools → States.
    # ------------------------------------------------------------------

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {"buoy_id": self._buoy_id}

        # Expose the time column if present
        for time_key in ("time", "Time", "date", "Date", "datetime", "Datetime"):
            if time_key in data:
                attrs["observation_time"] = data[time_key]
                break

        return attrs
