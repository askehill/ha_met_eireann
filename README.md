# Met Éireann Irish Sea Buoy — Home Assistant Custom Component

Pulls the latest buoy observations from Met.ie's public CSV endpoint and
exposes each measurement column as a Home Assistant sensor entity.  Data is
refreshed once per hour (configurable).

Optionally adds **tidal prediction sensors** — height, state, and next
high/low tide — computed locally using harmonic analysis with Admiralty Tide
Table constants.  No extra API or internet access needed for tides.

---

## Supported buoys

| ID | Location |
|----|----------|
| M2 | Irish Sea (east coast) |
| M3 | Atlantic (west coast) |
| M4 | Atlantic (west coast) |
| M5 | Atlantic (west coast) |
| M6 | Atlantic (west coast) |

---

## Installation

1. Copy all files into your Home Assistant `<config>/custom_components/met_ie_buoy/` directory:

   ```
   <config>/
   └── custom_components/
       └── met_ie_buoy/
           ├── __init__.py
           ├── manifest.json
           ├── const.py
           ├── coordinator.py
           ├── sensor.py
           └── tides.py
   ```

2. Add the following to your `configuration.yaml`:

   ```yaml
   sensor:
     - platform: met_ie_buoy
       buoy_id: M2
       name: "M2 Buoy"          # optional — prefix for all sensor names
       update_interval: 3600   # optional — seconds between buoy refreshes (default: 3600)
       tide_port: dublin        # optional — enables tide sensors (see ports below)
   ```

3. Restart Home Assistant.

---

## Buoy sensors

The integration reads the CSV headers on first load and creates one sensor per
measurement column.  Typical sensors for the M2 buoy:

| Entity ID | Description | Unit |
|-----------|-------------|------|
| `sensor.m2_buoy_significant_wave_height` | Significant wave height (Hm0) | m |
| `sensor.m2_buoy_peak_wave_period` | Peak wave period (Tp) | s |
| `sensor.m2_buoy_mean_wave_direction` | Mean wave direction | ° |
| `sensor.m2_buoy_sea_temperature` | Sea surface temperature | °C |
| `sensor.m2_buoy_air_temperature` | Air temperature | °C |
| `sensor.m2_buoy_wind_speed` | Wind speed | m/s |
| `sensor.m2_buoy_wind_gust` | Wind gust speed | m/s |
| `sensor.m2_buoy_wind_direction` | Wind direction | ° |
| `sensor.m2_buoy_atmospheric_pressure` | Atmospheric pressure | hPa |
| `sensor.m2_buoy_dew_point` | Dew point temperature | °C |

Any column not listed in `const.py → SENSOR_METADATA` still gets a sensor —
it just won't have units or a device class attached.

Every buoy sensor carries two extra attributes:
- **`buoy_id`** — the buoy identifier (e.g. `M2`)
- **`observation_time`** — timestamp of the reading from the CSV `time` column

---

## Tide sensors

When `tide_port` is set, four additional sensors are created (refreshed every
5 minutes using local harmonic computation — no network request):

| Sensor | State | Unit | Key attributes |
|--------|-------|------|----------------|
| `… Tide Height` | Current predicted height above Chart Datum | m | `tide_state`, `port`, `mhws`, `mlws` |
| `… Tide State` | `Rising` or `Falling` | — | `height_m`, `port` |
| `… Tide Next High` | Minutes until next high tide | min | `high_tide_time`, `high_tide_height` |
| `… Tide Next Low` | Minutes until next low tide | min | `low_tide_time`, `low_tide_height` |

### Supported tide ports

| Key | Port |
|-----|------|
| `dublin` | Dublin Port |
| `dun_laoghaire` | Dún Laoghaire |
| `cork` | Cork Harbour (Cobh) |
| `galway` | Galway |
| `westport` | Westport |
| `sligo` | Sligo |

> **Accuracy**: ±15 cm height, ±10 min timing (typical).  Uses a 5-constituent
> harmonic model (M2, S2, N2, K1, O1) with Admiralty Tide Table constants.
> Nodal corrections are not applied, so accuracy degrades slightly near the
> extremes of the 18.6-year nodal cycle.

---

## Automation examples

```yaml
# Alert when wave height exceeds 4 m
automation:
  - alias: "High waves warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.m2_buoy_significant_wave_height
        above: 4
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: >
            M2 buoy: wave height {{ states('sensor.m2_buoy_significant_wave_height') }} m

# Morning tide briefing
  - alias: "Morning tide briefing"
    trigger:
      - platform: time
        at: "07:30:00"
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: >
            Tide is {{ states('sensor.m2_buoy_tide_state') | lower }},
            currently {{ states('sensor.m2_buoy_tide_height') }} m.
            Next high in {{ states('sensor.m2_buoy_tide_next_high') }} min
            ({{ state_attr('sensor.m2_buoy_tide_next_high', 'high_tide_height') }} m).
```

---

## Troubleshooting

- Check **Settings → System → Logs** for lines containing `met_ie_buoy`.
- If no buoy sensors appear after restart, the first CSV fetch likely failed —
  look for `UpdateFailed` errors in the logs.
- Make sure your Home Assistant instance has outbound internet access to
  `www.met.ie` (only needed for buoy data, not tides).
- If tide times look wrong by a fixed offset, check that your HA timezone is
  set correctly — tide times are returned as UTC and converted by the frontend.
