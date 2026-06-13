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
    CONF_SWIM_WAVE_THRESHOLD,
    CONF_TIDE_PORT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BUOY_ID,
    DEFAULT_NAME,
    DEFAULT_SWIM_WAVE_THRESHOLD,
    DEFAULT_TIDE_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    PRIMARY_COLUMNS,
    SENSOR_METADATA,
    SWIM_ROUGH_WAVE_THRESHOLD,
    SWIM_TIDE_WINDOW_MINUTES,
)
from .coordinator import MetIeBuoyCoordinator
from .tides import PORTS, TidalPredictor, is_daylight

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
        vol.Optional(CONF_SWIM_WAVE_THRESHOLD, default=DEFAULT_SWIM_WAVE_THRESHOLD): vol.Coerce(float),
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
    swim_wave_threshold: float = config[CONF_SWIM_WAVE_THRESHOLD]

    # ── Buoy sensors ────────────────────────────────────────────────────────
    buoy_coordinator = MetIeBuoyCoordinator(hass, buoy_id, update_interval)
    await buoy_coordinator.async_refresh()

    if buoy_coordinator.last_exception:
        # Log but continue — tide sensors don't depend on buoy data and should
        # always load. Buoy measurement sensors will be missing until the next
        # HA restart once the server recovers (column discovery requires at
        # least one successful fetch).
        _LOGGER.warning(
            "Initial fetch for buoy %s failed (%s) — buoy measurement sensors "
            "will not be created until a successful fetch is possible. "
            "Tide and swim sensors will still load.",
            buoy_id,
            buoy_coordinator.last_exception,
        )

    # Use columns from the live CSV if available; fall back to the known primary
    # column list so sensors are always registered at startup.  They will show
    # as unknown until data arrives, then populate automatically — no restart
    # needed once the server recovers.
    discovered = {
        col for col in (buoy_coordinator.data or {})
        if col.lower() not in _SKIP_COLUMNS
    }
    columns_to_register = discovered or set(PRIMARY_COLUMNS)

    if not discovered:
        _LOGGER.warning(
            "No columns discovered for buoy %s — pre-registering known sensors; "
            "they will populate once the server returns data",
            buoy_id,
        )

    entities: list[SensorEntity] = []
    for column in columns_to_register:
        entities.append(
            MetIeBuoySensor(
                coordinator=buoy_coordinator,
                column=column,
                platform_name=platform_name,
                buoy_id=buoy_id,
            )
        )

    # Always add a last-fetch timestamp sensor so users can see at a glance
    # whether buoy data is current or stale.
    entities.append(
        BuoyLastFetchSensor(
            coordinator=buoy_coordinator,
            platform_name=platform_name,
            buoy_id=buoy_id,
        )
    )

    _LOGGER.info(
        "Met.ie buoy %s: adding %d measurement sensors (%s)",
        buoy_id,
        len(entities) - 1,  # exclude the last-fetch sensor from the count
        "from live data" if discovered else "from fallback column list",
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
        try:
            # First refresh is cheap (pure maths, no network)
            await tide_coordinator.async_refresh()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "Initial tide calculation for port '%s' failed (%s) — "
                "tide sensors will be unavailable until the next poll",
                tide_port_key,
                err,
            )

        tide_prefix = f"{platform_name} Tide"
        entities += [
            TideHeightSensor(tide_coordinator, tide_prefix, buoy_id, tide_port_key),
            TideStateSensor(tide_coordinator, tide_prefix, buoy_id, tide_port_key),
            TideNextHighSensor(tide_coordinator, tide_prefix, buoy_id, tide_port_key),
            TideNextHighTimeSensor(tide_coordinator, tide_prefix, buoy_id, tide_port_key),
            TideNextLowSensor(tide_coordinator, tide_prefix, buoy_id, tide_port_key),
            TideNextLowTimeSensor(tide_coordinator, tide_prefix, buoy_id, tide_port_key),
            TideForecastSensor(tide_coordinator, tide_prefix, buoy_id, tide_port_key),
            SwimConditionSensor(
                tide_coordinator, buoy_coordinator,
                platform_name, buoy_id, tide_port_key,
                swim_wave_threshold,
            ),
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
# Buoy last-fetch timestamp sensor
# ---------------------------------------------------------------------------

class BuoyLastFetchSensor(SensorEntity):
    """Timestamp of the most recent successful data fetch from the buoy CSV.

    Deliberately does NOT inherit CoordinatorEntity — that base class ties
    availability to coordinator.last_update_success, which would cause this
    sensor to show as unavailable whenever the buoy fetch fails.  Instead we
    wire up the coordinator listener ourselves so we control availability
    independently and always show 'unknown' (not 'unavailable') before the
    first good fetch arrives.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_should_poll = False
    _attr_has_entity_name = False
    _attr_icon = "mdi:clock-check-outline"
    _attr_available = True

    def __init__(
        self,
        coordinator: MetIeBuoyCoordinator,
        platform_name: str,
        buoy_id: str,
    ) -> None:
        self._coordinator = coordinator
        self._buoy_id = buoy_id
        self._attr_name = f"{platform_name} Last Updated"
        self._attr_unique_id = f"{DOMAIN}_{buoy_id}_last_fetch"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def native_value(self) -> datetime | None:
        return self._coordinator.last_fetch_time


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


# ---------------------------------------------------------------------------
# Next high tide TIME sensor
# ---------------------------------------------------------------------------

class TideNextHighTimeSensor(_TideSensorBase):
    """Timestamp of the next high tide."""

    _attr_icon = "mdi:wave-arrow-up"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, prefix, buoy_id, port_key):
        super().__init__(
            coordinator, prefix, buoy_id, port_key,
            suffix="Next High Time", unique_suffix="next_high_time",
        )

    @property
    def native_value(self) -> datetime | None:
        return self._tide.get("next_high_time")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self._tide
        return {
            "high_tide_height": t.get("next_high_height"),
            "port":             t.get("port"),
        }


# ---------------------------------------------------------------------------
# Next low tide TIME sensor
# ---------------------------------------------------------------------------

class TideNextLowTimeSensor(_TideSensorBase):
    """Timestamp of the next low tide."""

    _attr_icon = "mdi:wave-arrow-down"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, prefix, buoy_id, port_key):
        super().__init__(
            coordinator, prefix, buoy_id, port_key,
            suffix="Next Low Time", unique_suffix="next_low_time",
        )

    @property
    def native_value(self) -> datetime | None:
        return self._tide.get("next_low_time")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self._tide
        return {
            "low_tide_height": t.get("next_low_height"),
            "port":            t.get("port"),
        }


# ---------------------------------------------------------------------------
# Tide forecast sensor  (drives the ApexCharts card)
# ---------------------------------------------------------------------------

class TideForecastSensor(_TideSensorBase):
    """
    Exposes the 72-hour tide forecast as sensor attributes for charting.

    State  : current tide height (m) — same value as TideHeightSensor.
    Attributes:
      forecast        list[{t, h}]           30-min curve over 72 hours
      upcoming_highs  list[{time, height}]   next 6 high tides (~3 days)
      upcoming_lows   list[{time, height}]   next 6 low tides  (~3 days)
      port            str
    """

    _attr_icon = "mdi:chart-bell-curve"
    _attr_native_unit_of_measurement = "m"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, prefix, buoy_id, port_key):
        super().__init__(
            coordinator, prefix, buoy_id, port_key,
            suffix="Forecast", unique_suffix="forecast",
        )

    @property
    def native_value(self) -> float | None:
        return self._tide.get("height")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t = self._tide
        return {
            "forecast":       t.get("forecast", []),
            "upcoming_highs": t.get("upcoming_highs", []),
            "upcoming_lows":  t.get("upcoming_lows", []),
            "port":           t.get("port"),
        }


# ---------------------------------------------------------------------------
# Swim condition sensor
# ---------------------------------------------------------------------------

class SwimConditionSensor(_TideSensorBase):
    """
    Indicates whether conditions are good for a swim.

    "Perfect"  — daylight AND within SWIM_TIDE_WINDOW_MINUTES of high tide
                 AND wave height at or below the configured threshold (1.0 m default).
    "Choppy"   — daylight AND within SWIM_TIDE_WINDOW_MINUTES of high tide
                 AND wave height between the threshold and 1.75 m.
    "Rough"    — daylight AND within SWIM_TIDE_WINDOW_MINUTES of high tide
                 AND wave height above 1.75 m.
    "Moderate" — daylight AND within SWIM_TIDE_WINDOW_MINUTES of high tide
                 BUT wave height not yet available from the buoy.
    "Poor"     — any other case (wrong tide, waves too high, or after dark).

    Reads tide data from the TideCoordinator and wave height from the
    MetIeBuoyCoordinator (the `height` CSV column).
    """

    _attr_icon = "mdi:swim"

    def __init__(
        self,
        tide_coordinator: TideCoordinator,
        buoy_coordinator: MetIeBuoyCoordinator,
        prefix: str,
        buoy_id: str,
        port_key: str,
        wave_threshold: float,
    ) -> None:
        super().__init__(
            tide_coordinator, prefix, buoy_id, port_key,
            suffix="Swim Condition", unique_suffix="swim_condition",
        )
        self._buoy_coordinator = buoy_coordinator
        self._wave_threshold = wave_threshold

    # Subscribe to both coordinators so the entity refreshes when either updates
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._buoy_coordinator.async_add_listener(self.async_write_ha_state)
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def _wave_height(self) -> float | None:
        """Current significant wave height from the buoy CSV (metres)."""
        data = self._buoy_coordinator.data or {}
        raw = data.get("height")
        if raw is None or str(raw).strip() in ("", "NaN", "N/A", "null", "NULL"):
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    @property
    def _near_high_tide(self) -> bool:
        """True if within SWIM_TIDE_WINDOW_MINUTES of the nearest high tide."""
        t = self._tide
        mins_to    = t.get("minutes_to_high")
        mins_since = t.get("minutes_since_high")
        approaching = mins_to    is not None and mins_to    <= SWIM_TIDE_WINDOW_MINUTES
        just_passed = mins_since is not None and mins_since <= SWIM_TIDE_WINDOW_MINUTES
        return approaching or just_passed

    @property
    def _is_daylight(self) -> bool:
        """True if the current time falls between sunrise and sunset at the tide port."""
        port = PORTS.get(self._port_key)
        if port is None:
            return True  # no port data — don't penalise
        return is_daylight(datetime.now(timezone.utc), lat=port.lat, lon=port.lon)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def native_value(self) -> str:
        tide_ok = self._near_high_tide
        day_ok  = self._is_daylight
        wave    = self._wave_height

        if day_ok and tide_ok and wave is not None:
            if wave <= self._wave_threshold:
                return "Perfect"
            if wave <= SWIM_ROUGH_WAVE_THRESHOLD:
                return "Choppy"
            return "Rough"
        if day_ok and tide_ok and wave is None:
            return "Moderate"
        return "Poor"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        t          = self._tide
        wave       = self._wave_height
        mins_to    = t.get("minutes_to_high")
        mins_since = t.get("minutes_since_high")
        day_ok     = self._is_daylight
        tide_ok    = self._near_high_tide

        reasons: list[str] = []
        if not day_ok:
            reasons.append("outside daylight hours")
        if not tide_ok:
            if mins_to is not None:
                reasons.append(
                    f"high tide is {mins_to} min away (window is ±{SWIM_TIDE_WINDOW_MINUTES} min)"
                )
        if wave is not None and wave > SWIM_ROUGH_WAVE_THRESHOLD:
            reasons.append(f"waves {wave} m are rough (above {SWIM_ROUGH_WAVE_THRESHOLD} m)")
        elif wave is not None and wave > self._wave_threshold:
            reasons.append(f"waves {wave} m are choppy (above {self._wave_threshold} m)")
        if wave is None and (day_ok and tide_ok):
            reasons.append("wave height not yet available — conditions otherwise ok")

        return {
            "is_daylight":           day_ok,
            "near_high_tide":        tide_ok,
            "minutes_to_high_tide":  mins_to,
            "minutes_since_high_tide": mins_since,
            "wave_height_m":         wave,
            "wave_threshold_m":      self._wave_threshold,
            "reason":                "; ".join(reasons) if reasons else "all conditions met",
            "port":                  t.get("port"),
        }
