"""Constants for the Met Éireann Irish Sea Buoy integration."""

DOMAIN = "met_ie_buoy"

# Download URL — append buoy ID (e.g. M2, M3, M4, M5, M6)
BASE_URL = "https://www.met.ie/forecasts/marine-inland-lakes/buoys/download/"

DEFAULT_BUOY_ID = "M2"
DEFAULT_NAME = "Met.ie Buoy"
DEFAULT_UPDATE_INTERVAL = 3600  # seconds (1 hour)

CONF_BUOY_ID = "buoy_id"
CONF_UPDATE_INTERVAL = "update_interval"  # custom key — avoids clash with HA's reserved 'scan_interval'
CONF_TIDE_PORT = "tide_port"
CONF_SWIM_WAVE_THRESHOLD = "swim_wave_threshold"

DEFAULT_TIDE_UPDATE_INTERVAL = 300   # seconds (5 minutes) — pure local computation
DEFAULT_SWIM_WAVE_THRESHOLD  = 1.0   # metres — Hm0 above this is considered too rough
SWIM_TIDE_WINDOW_MINUTES     = 90    # minutes either side of high tide

# ---------------------------------------------------------------------------
# Known column → (friendly name, unit_of_measurement, device_class, icon)
# The integration discovers columns dynamically; this dict provides nicer
# metadata for recognised field names.  Unknown columns still get sensors,
# just without units / device class.
# ---------------------------------------------------------------------------
SENSOR_METADATA: dict[str, tuple[str, str | None, str | None, str]] = {
    # ── Actual Met.ie CSV column names (confirmed from live data) ────────────
    # Atmospheric
    "pressure":     ("Atmospheric Pressure",    "hPa",  "atmospheric_pressure", "mdi:gauge"),
    # Wind  (speeds reported in knots by Met.ie marine stations)
    "windSpeed":    ("Wind Speed",              "kn",   "wind_speed",           "mdi:weather-windy"),
    "windGust":     ("Wind Gust",               "kn",   "wind_speed",           "mdi:weather-windy"),
    "windDir":      ("Wind Direction",          "°",    None,                   "mdi:compass-rose"),
    "windGustDir":  ("Wind Gust Direction",     "°",    None,                   "mdi:compass-rose"),
    # Temperature
    "temp":         ("Air Temperature",         "°C",   "temperature",          "mdi:thermometer"),
    "dewPoint":     ("Dew Point",               "°C",   "temperature",          "mdi:thermometer-water"),
    "humidity":     ("Relative Humidity",       "%",    "humidity",             "mdi:water-percent"),
    "seaTemp":      ("Sea Temperature",         "°C",   "temperature",          "mdi:thermometer"),
    # Waves
    "height":       ("Significant Wave Height", "m",    None,                   "mdi:waves"),
    "period":       ("Wave Peak Period",        "s",    None,                   "mdi:sine-wave"),
    "waveDir":      ("Wave Direction",          "°",    None,                   "mdi:compass-rose"),

    # ── Legacy / alternative column names (other buoy CSV variants) ──────────
    "AtmPressure":  ("Atmospheric Pressure",    "hPa",  "atmospheric_pressure", "mdi:gauge"),
    "WindSpeed":    ("Wind Speed",              "kn",   "wind_speed",           "mdi:weather-windy"),
    "WindGust":     ("Wind Gust",               "kn",   "wind_speed",           "mdi:weather-windy"),
    "WindDirection":("Wind Direction",          "°",    None,                   "mdi:compass-rose"),
    "Gust_Dir":     ("Wind Gust Direction",     "°",    None,                   "mdi:compass-rose"),
    "AirTemperature":("Air Temperature",        "°C",   "temperature",          "mdi:thermometer"),
    "AirTemp":      ("Air Temperature",         "°C",   "temperature",          "mdi:thermometer"),
    "DewPoint":     ("Dew Point",               "°C",   "temperature",          "mdi:thermometer-water"),
    "SeaTemperature":("Sea Temperature",        "°C",   "temperature",          "mdi:thermometer"),
    "SeaTemp":      ("Sea Temperature",         "°C",   "temperature",          "mdi:thermometer"),
    "Hm0":          ("Significant Wave Height", "m",    None,                   "mdi:waves"),
    "Tp":           ("Wave Peak Period",        "s",    None,                   "mdi:sine-wave"),
    "Tz":           ("Wave Mean Period",        "s",    None,                   "mdi:sine-wave"),
    "MeanPeriod":   ("Wave Mean Period",        "s",    None,                   "mdi:sine-wave"),
    "PeakPeriod":   ("Wave Peak Period",        "s",    None,                   "mdi:sine-wave"),
    "MeanDirection":("Mean Wave Direction",     "°",    None,                   "mdi:compass-rose"),
    "WaveDirection":("Wave Direction",          "°",    None,                   "mdi:compass-rose"),
    "Humidity":     ("Relative Humidity",       "%",    "humidity",             "mdi:water-percent"),
    "Visibility":   ("Visibility",              "km",   None,                   "mdi:eye"),
}
