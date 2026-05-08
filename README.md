# Met Éireann Irish Sea Buoy — Home Assistant Custom Component

Pulls the latest buoy observations from Met.ie's public CSV endpoint and
exposes each measurement column as a Home Assistant sensor entity.  Data
is refreshed once per hour (configurable).

## Supported buoys

| ID | Location |
|----|----------|
| M2 | Irish Sea (east coast) |
| M3 | Atlantic (west coast) |
| M4 | Atlantic (west coast) |
| M5 | Atlantic (west coast) |
| M6 | Atlantic (west coast) |

## Installation

1. Copy the `met_ie_buoy/` folder into your Home Assistant
   `<config>/custom_components/` directory:

   ```
   <config>/
   └── custom_components/
       └── met_ie_buoy/
           ├── __init__.py
           ├── manifest.json
           ├── const.py
           ├── coordinator.py
           └── sensor.py
   ```

2. Add the following to your `configuration.yaml`:

   ```yaml
   sensor:
     - platform: met_ie_buoy
       buoy_id: M2
       name: "M2 Buoy"        # optional — becomes the prefix for all sensor names
       scan_interval: 3600    # optional — seconds between refreshes (default: 3600)
   ```

3. Restart Home Assistant.

## Sensors created

The integration reads the CSV headers on first load and creates one sensor per
measurement column.  Typical sensors for the M2 buoy include:

| Entity ID | Description | Unit |
|-----------|-------------|------|
| `sensor.m2_buoy_significant_wave_height` | Hm0 | m |
| `sensor.m2_buoy_peak_wave_period` | Tp | s |
| `sensor.m2_buoy_mean_wave_direction` | ° | ° |
| `sensor.m2_buoy_sea_temperature` | °C | °C |
| `sensor.m2_buoy_air_temperature` | °C | °C |
| `sensor.m2_buoy_wind_speed` | m/s | m/s |
| `sensor.m2_buoy_wind_gust` | m/s | m/s |
| `sensor.m2_buoy_wind_direction` | ° | ° |
| `sensor.m2_buoy_atmospheric_pressure` | hPa | hPa |
| `sensor.m2_buoy_dew_point` | °C | °C |

> The exact sensors depend on what the CSV currently contains.  Any column
> not listed in `const.py → SENSOR_METADATA` will still get a sensor — it
> just won't have units or a device class attached.

## Attributes

Every sensor carries two extra attributes:

- **`buoy_id`** — the buoy identifier (e.g. `M2`)
- **`observation_time`** — the timestamp of the reading, taken from the
  `time` / `date` column of the CSV

## Using in automations / Lovelace

```yaml
# Example: alert when significant wave height exceeds 4 m
automation:
  - alias: "High waves warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.m2_buoy_significant_wave_height
        above: 4
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "M2 buoy: wave height {{ states('sensor.m2_buoy_significant_wave_height') }} m"
```

## Troubleshooting

- Check **Settings → System → Logs** for lines containing `met_ie_buoy`.
- If no sensors appear after restart, the first CSV fetch may have failed —
  look for `UpdateFailed` errors in the logs.
- Make sure your Home Assistant instance has outbound internet access to
  `www.met.ie`.
