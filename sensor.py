"""Sensor platform for the Met Éireann Irish Sea Buoy integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    CONF_BUOY_ID,
    CONF_TIDE_PORT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BUOY_ID,
    DEFAULT_NAME,
    DEFAULT_TIDE_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SENSOR_METADATA,
)
from .coordinator import MetIeBuoyCoordinator
from .tides import PORTS, TidalPredictor

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# YAML platform schema
# ---------------------------------------------------------------------------
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_BUOY_ID, default=DEFAULT_BUOY_ID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): cv.positive_int,
        vol.Optional(CONF_TIDE_PORT): vol.In(list(PORTS.keys())),
    }
)

# Columns that are metadata / timestamps — skip creating sensors for these.
# The "time" column is surfaced as an attribute on every buoy sensor.
_SKIP_COLUMNS = {
    # Identifiers
    "id", "name", "wmoid", "wmoID",
    "stationid", "station_id", "stationname", "station_name",
    "buoyid", "buoy_id", "buoy", "station",
    # Timestamps / audit fields
    "time", "date", "datetime", "timestamp",
    "reportdate", "reporttime",
    "updated_at", "created_at",
    # Location
    "location", "latitude", "longitude", "lat", "lon",
}

# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Met.ie buoy (and optional tide) sensors from configuration.yaml."""
    buoy_id: str = config[CONF_BUOY_ID]
    platform_name: str = config[CONF_NAME]
    update_interval: int = config[CONF_UPDATE_INTERVAL]
    tide_port_key: str | None = config.get(CONF_TIDE_PORT)

    # ── Buoy sensors ────────────────────────────────────────────────────────
    buoy_coordinator = MetIeBuoyCoordinator(hass, buoy_id, update_interval)
    await buoy_coordinator.async_refresh()

    if buoy_coordinator.last_exception:
        _LOGGER.error(
            "Initial fetch for buoy %s failed: %s",
            buoy_id,
            buoy_coordinator.last_exception,
        )
        return

    entities: list[SensorEntity] = []
    for column in buoy_coordinator.data or {}:
        if column.lower() in _SKIP_COLUMNS:
            continue
        entities.append(
            MetIeBuoySensor(
                coordinator=buoy_coordinator,
                column=column,
                platform_name=platform_name,
                buoy_id=buoy_id,
            )
        )

    if not entities:
        _LOGGER.warning("No sensor columns discovered for buoy %s", buoy_id)
    else:
        _LOGGER.info(
            "Met.ie buoy %s: adding %d measurement sensors",
            buoy_id,
            len(entities),
        )

    # ── Tide sensors (optional) ─────────────────────────────────────────────
    if tide_port_key:
        port = PORTS[tide_port_key]
        predictor = TidalPredictor(port)
        _LOGGER.info(
            "Met.ie buoy %s: enabling tide sensors for '%s'",
            buoy_id,
            port.name,
        )

        tide_coordinator = TideCoordinator(hass, predictor, buoy_id, tide_port_key)
        # First refresh is cheap (pure maths, no network)
        await tide_coordinator.async_refresh()

        tide_prefix = f"{platform_name} Tide"
        entities += [
            TideHeightSensor(tide_coordinator, tide_prefix, buoy_id, tide_port_key),
            TideStateSensor(tide_coordinator, tide_prefix, buoy_id, tide_port_key),
            TideNextHighSensor(tide_coordinator, tide_prefix, buoy_id, tide_port_key),
            TideNextLowSensor(tide_coordinator, tide_prefix, buoy_id, tide_port_key),
        ]

    async_add_entities(entities, update_before_add=False)


# ---------------------------------------------------------------------------
# Buoy measurement sensor
# ---------------------------------------------------------------------------

class MetIeBuoySensor(CoordinatorEntity[MetIeBuoyCoordinator], SensorEntity):
    """A single measurement column from the Met.ie buoy CSV."""

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
            self._attr_name = f"{platform_name} {column}"
            self._attr_native_unit_of_measurement = None
            self._attr_device_class = None
            self._attr_icon = "mdi:chart-line"

        self._attr_unique_id = (
            f"{DOMAIN}_{buoy_id}_{column.lower().replace(' ', '_')}"
        )

    @property
    def native_value(self) -> float | str | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self._column)
        if raw is None or raw.strip() in ("", "NaN", "N/A", "null", "NULL"):
            return None
        try:
            return float(raw)
        except ValueError:
            return raw

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {"buoy_id": self._buoy_id}
        for time_key in ("time", "Time", "date", "Date", "datetime", "Datetime"):
            if time_key in data:
                attrs["observation_time"] = data[time_key]
                break
        return attrs


# ---------------------------------------------------------------------------
# Tide coordinator (local computation — no network)
# ---------------------------------------------------------------------------

class TideCoordinator(DataUpdateCoordinator[dict]):
    """
    Refreshes tidal state every 5 minutes using pure harmonic computation.
    No network requests are made — this is entirely local maths.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        predictor: TidalPredictor,
        buoy_id: str,
        port_key: str,
    ) -> None:
        self._predictor = predictor
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_tide_{buoy_id}_{port_key}",
            update_interval=timedelta(seconds=DEFAULT_TIDE_UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> dict:
        """Compute tidal state for the current UTC time (runs in executor)."""
        now = datetime.now(timezone.utc)
        return await self.hass.async_add_executor_job(
            self._predictor.state, now
        )


# ---------------------------------------------------------------------------
# Tide sensor base
# ---------------------------------------------------------------------------

class _TideSensorBase(CoordinatorEntity[TideCoordinator], SensorEntity):
    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TideCoordinator,
        prefix: str,
        buoy_id: str,
        port_key: str,
        suffix: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._buoy_id = buoy_id
        self._port_key = port_key
        self._attr_name = f"{prefix} {suffix}"
        self._attr_unique_id = (
            f"{DOMAIN}_{buoy_id}_tide_{unique_suffix}"
        )

    @property
    def _tide(self) -> dict:
        return self.coordinator.data or {}


# ---------------------------------------------------------------------------
# Tide height sensor
# ---------------------------------------------------------------------------

class TideHeightSensor(_TideSensorBase):
    """Current predicted tidal height above Chart Datum (m)."""

    _attr_icon = "mdi:waves"
    _attr_native_unit_of_measurement = "m"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, prefix, buoy_id, port_key):
        super().__init__(
            coordinator, prefix, buoy_id, port_key,
            suffix="Height", unique_suffix="height",
        )

    @property
    def native_value(self) -> float | None:
        return self._tide.get("height")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self._tide
        return {
            "tide_state": t.get("state"),
            "port":        t.get("port"),
            "mhws":        t.get("mhws"),
            "mlws":        t.get("mlws"),
        }


# ---------------------------------------------------------------------------
# Tide state sensor  (Rising / Falling)
# ---------------------------------------------------------------------------

class TideStateSensor(_TideSensorBase):
    """Whether the tide is currently rising or falling."""

    _attr_icon = "mdi:transfer-up"

    def __init__(self, coordinator, prefix, buoy_id, port_key):
        super().__init__(
            coordinator, prefix, buoy_id, port_key,
            suffix="State", unique_suffix="state",
        )

    @property
    def native_value(self) -> str | None:
        state = self._tide.get("state")
        # Update icon to match direction
        if state == "Rising":
            self._attr_icon = "mdi:transfer-up"
        elif state == "Falling":
            self._attr_icon = "mdi:transfer-down"
        return state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self._tide
        return {
            "height_m":      t.get("height"),
            "port":          t.get("port"),
        }


# ---------------------------------------------------------------------------
# Next high tide sensor
# ---------------------------------------------------------------------------

class TideNextHighSensor(_TideSensorBase):
    """Minutes until the next high tide."""

    _attr_icon = "mdi:wave-arrow-up"
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, prefix, buoy_id, port_key):
        super().__init__(
            coordinator, prefix, buoy_id, port_key,
            suffix="Next High", unique_suffix="next_high",
        )

    @property
    def native_value(self) -> int | None:
        return self._tide.get("minutes_to_high")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self._tide
        high_time: datetime | None = t.get("next_high_time")
        return {
            "high_tide_time":   high_time.isoformat() if high_time else None,
            "high_tide_height": t.get("next_high_height"),
            "port":             t.get("port"),
        }


# ---------------------------------------------------------------------------
# Next low tide sensor
# ---------------------------------------------------------------------------

class TideNextLowSensor(_TideSensorBase):
    """Minutes until the next low tide."""

    _attr_icon = "mdi:wave-arrow-down"
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, prefix, buoy_id, port_key):
        super().__init__(
            coordinator, prefix, buoy_id, port_key,
            suffix="Next Low", unique_suffix="next_low",
        )

    @property
    def native_value(self) -> int | None:
        return self._tide.get("minutes_to_low")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self._tide
        low_time: datetime | None = t.get("next_low_time")
        return {
            "low_tide_time":   low_time.isoformat() if low_time else None,
            "low_tide_height": t.get("next_low_height"),
            "port":            t.get("port"),
        }
