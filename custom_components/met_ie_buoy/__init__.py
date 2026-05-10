"""Met Éireann Irish Sea Buoy — custom component for Home Assistant.

Provides sensor entities for the latest readings from Met.ie buoy CSV feeds.
Each CSV column (wave height, sea/air temperature, wind speed, etc.) becomes
its own sensor, updated once per hour.

Configuration (configuration.yaml):

    sensor:
      - platform: met_ie_buoy
        buoy_id: M2          # M2, M3, M4, M5 or M6
        name: "M2 Buoy"      # optional — prefix for sensor names
        scan_interval: 3600  # optional — seconds between refreshes (default 3600)
"""

DOMAIN = "met_ie_buoy"
