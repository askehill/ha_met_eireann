"""Constants for the Met Éireann Irish Sea Buoy integration."""

DOMAIN = "met_ie_buoy"

# Download URL — append buoy ID (e.g. M2, M3, M4, M5, M6)
BASE_URL = "https://www.met.ie/forecasts/marine-inland-lakes/buoys/download/"

DEFAULT_BUOY_ID = "M2"
DEFAULT_NAME = "Met.ie Buoy"
DEFAULT_SCAN_INTERVAL = 3600  # seconds (1 hour)

CONF_BUOY_ID = "buoy_id"

# ---------------------------------------------------------------------------
# Known column → (friendly name, unit_of_measurement, device_class, icon)
# The integration discovers columns dynamically; this dict provides nicer
# metadata for recognised field names.  Unknown columns still get sensors,
# just without units / device class.
# ---------------------------------------------------------------------------
SENSOR_METADATA: dict[str, tuple[str, str | None, str | None, str]] = {
    # Atmospheric
    "AtmPressure":      ("Atmospheric Pressure",    "hPa",   "atmospheric_pressure", "mdi:gauge"),
    # Wind
    "WindSpeed":        ("Wind Speed",              "m/s",   "wind_speed",            "mdi:weather-windy"),
    "WindGust":         ("Wind Gust",               "m/s",   "wind_speed",            "mdi:weather-windy"),
    "WindDirection":    ("Wind Direction",           "°",     None,                    "mdi:compass-rose"),
    "Gust_Dir":         ("Gust Direction",           "°",     None,                    "mdi:compass-rose"),
    # Temperature
    "AirTemperature":   ("Air Temperature",         "°C",    "temperature",           "mdi:thermometer"),
    "AirTemp":          ("Air Temperature",         "°C",    "temperature",           "mdi:thermometer"),
    "DewPoint":         ("Dew Point",               "°C",    "temperature",           "mdi:thermometer-water"),
    "SeaTemperature":   ("Sea Temperature",         "°C",    "temperature",           "mdi:thermometer"),
    "SeaTemp":          ("Sea Temperature",         "°C",    "temperature",           "mdi:thermometer"),
    # Waves
    "Hm0":              ("Significant Wave Height", "m",     None,                    "mdi:waves"),
    "Tp":               ("Peak Wave Period",         "s",     None,                    "mdi:sine-wave"),
    "Tz":               ("Mean Zero-Crossing Period","s",     None,                    "mdi:sine-wave"),
    "MeanPeriod":       ("Mean Wave Period",         "s",     None,                    "mdi:sine-wave"),
    "PeakPeriod":       ("Peak Wave Period",         "s",     None,                    "mdi:sine-wave"),
    "MeanDirection":    ("Mean Wave Direction",      "°",     None,                    "mdi:compass-rose"),
    "WaveDirection":    ("Wave Direction",           "°",     None,                    "mdi:compass-rose"),
    "HarmonicMean":     ("Harmonic Mean Period",     "s",     None,                    "mdi:sine-wave"),
    # Misc
    "Visibility":       ("Visibility",              "km",    None,                    "mdi:eye"),
    "Humidity":         ("Relative Humidity",       "%",     "humidity",              "mdi:water-percent"),
}
