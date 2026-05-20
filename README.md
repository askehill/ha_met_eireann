# Met Éireann Irish Sea Buoy — Home Assistant Custom Component

Pulls the latest buoy observations from Met.ie's public CSV endpoint and
exposes each measurement column as a Home Assistant sensor entity. Data is
refreshed once per hour (configurable).

Optionally adds **tidal prediction sensors** — current height, state, next
high/low tide times, a **72-hour forecast curve**, and a **swim condition
guide** — all computed locally using harmonic analysis with Admiralty Tide
Table constants. No extra API or internet access needed for tides.

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

1. Copy the `custom_components/met_ie_buoy/` folder into your Home Assistant
   config directory:

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
       name: "M2 Buoy"           # optional — prefix for all sensor names
       update_interval: 3600     # optional — seconds between buoy refreshes (default: 3600)
       tide_port: dublin          # optional — enables tide sensors (see ports below)
       swim_wave_threshold: 1.0  # optional — max wave height (m) for "Good" swim (default: 1.0)
   ```

3. Restart Home Assistant.

---

## Buoy sensors

The integration reads the CSV headers on first load and creates one sensor per
measurement column. Sensors for the M2 buoy (column names confirmed from live data):

| Entity ID | CSV column | Description | Unit |
|-----------|------------|-------------|------|
| `sensor.m2_buoy_atmospheric_pressure` | `pressure` | Atmospheric pressure | hPa |
| `sensor.m2_buoy_wind_direction` | `windDir` | Wind direction | ° |
| `sensor.m2_buoy_wind_speed` | `windSpeed` | Wind speed | kn |
| `sensor.m2_buoy_wind_gust` | `windGust` | Wind gust speed | kn |
| `sensor.m2_buoy_wind_gust_direction` | `windGustDir` | Wind gust direction | ° |
| `sensor.m2_buoy_air_temperature` | `temp` | Air temperature | °C |
| `sensor.m2_buoy_dew_point` | `dewPoint` | Dew point temperature | °C |
| `sensor.m2_buoy_relative_humidity` | `humidity` | Relative humidity | % |
| `sensor.m2_buoy_significant_wave_height` | `height` | Significant wave height | m |
| `sensor.m2_buoy_wave_peak_period` | `period` | Wave peak period | s |
| `sensor.m2_buoy_wave_direction` | `waveDir` | Wave direction | ° |
| `sensor.m2_buoy_sea_temperature` | `seaTemp` | Sea temperature | °C |

> Wind speeds are reported in **knots** by Met.ie marine stations.
> Some columns (e.g. `windGust`, `waveDir`) may show `unknown` in HA when the
> buoy hasn't reported a value for that reading.

Any column not listed in `const.py → SENSOR_METADATA` still gets a sensor —
it just won't have units or a device class attached.

Every buoy sensor carries two extra attributes:
- **`buoy_id`** — the buoy identifier (e.g. `M2`)
- **`observation_time`** — timestamp of the reading from the CSV `time` column

---

## Tide sensors

When `tide_port` is set, the following sensors are created (refreshed every
5 minutes using local harmonic computation — no network request):

| Sensor | State | Unit | Key attributes |
|--------|-------|------|----------------|
| `… Tide Height` | Current predicted height above Chart Datum | m | `tide_state`, `port`, `mhws`, `mlws` |
| `… Tide State` | `Rising` or `Falling` | — | `height_m`, `port` |
| `… Tide Next High` | Minutes until next high tide | min | `high_tide_time`, `high_tide_height` |
| `… Tide Next Low` | Minutes until next low tide | min | `low_tide_time`, `low_tide_height` |
| `… Tide Next High Time` | Time of next high tide | timestamp | `height` |
| `… Tide Next Low Time` | Time of next low tide | timestamp | `height` |
| `… Tide Forecast` | Current height | m | `forecast`, `upcoming_highs`, `upcoming_lows` |

### Forecast attributes

The **Tide Forecast** sensor's attributes contain everything needed to draw a
tide chart without additional API calls:

- **`forecast`** — list of 145 `{t, h}` points covering the next 72 hours at
  30-minute intervals, e.g. `[{"t": "2026-05-09T06:00:00+00:00", "h": 2.34}, …]`
- **`upcoming_highs`** — next 6 high tides as `[{"time": "…", "height": 4.12}, …]`
- **`upcoming_lows`** — next 6 low tides as `[{"time": "…", "height": 0.41}, …]`

### Supported tide ports

| Key | Port |
|-----|------|
| `dublin` | Dublin Port |
| `dun_laoghaire` | Dún Laoghaire |
| `cork` | Cork Harbour (Cobh) |
| `galway` | Galway |
| `westport` | Westport |
| `sligo` | Sligo |

> **Accuracy**: ±15 cm height, ±10 min timing (typical). Uses a 5-constituent
> harmonic model (M2, S2, N2, K1, O1) with Admiralty Tide Table constants.
> Nodal corrections are not applied, so accuracy degrades slightly near the
> extremes of the 18.6-year nodal cycle.

---

## Swim condition sensor

When `tide_port` is set, a **Swim Condition** sensor is also created. It
combines the buoy's wave height reading, the local tidal prediction, and
sunrise/sunset times to give a simple guide for open-water swimming:

| State | Meaning |
|-------|---------|
| `Good` | Daytime, within 90 minutes of high tide, **and** wave height ≤ threshold |
| `Moderate` | Daytime, within 90 minutes of high tide, but buoy wave data is unavailable |
| `Poor` | Outside the tide window, waves too high, or after dark |

The 90-minute window and wave height threshold are based on typical Irish
coastal swimming conditions — high tide brings clearer, deeper water inshore,
while the threshold filters out rough days. The daylight requirement means the
sensor will always return `Poor` at night regardless of tide or wave conditions.

**Key attributes:**

- **`reason`** — short explanation, e.g. `"Wave height 1.8 m exceeds threshold 1.0 m"`
- **`wave_height_m`** — the raw wave height from the buoy
- **`minutes_to_high`** / **`minutes_since_high`** — tide timing used in the calculation
- **`is_daylight`** — `true` if the current time is between sunrise and sunset

The wave height threshold defaults to `1.0 m` and can be overridden in
`configuration.yaml` with `swim_wave_threshold`.

---

## ApexCharts tide card

A ready-made Lovelace card config is included in `apexcharts_tide_card.yaml`.
It requires the [ApexCharts Card](https://github.com/RomRider/apexcharts-card)
HACS frontend integration.

The card shows:
- A smooth 72-hour tide height curve (blue line)
- Upcoming high tide markers with height labels (red dots)
- Upcoming low tide markers with height labels (green dots)

To use it, paste the contents of `apexcharts_tide_card.yaml` into a manual
card in your Lovelace dashboard and update the entity name if yours differs
from `sensor.m2_buoy_tide_forecast`.

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
            Next high in
            {{ (state_attr('sensor.m2_buoy_tide_next_high', 'high_tide_time') | as_datetime - now())
               .total_seconds() // 3600 | int }}h
            {{ ((state_attr('sensor.m2_buoy_tide_next_high', 'high_tide_time') | as_datetime - now())
               .total_seconds() % 3600) // 60 | int }}m
            ({{ state_attr('sensor.m2_buoy_tide_next_high', 'high_tide_height') }} m).
            Swim: {{ states('sensor.m2_buoy_swim_condition') }}.
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
- If the swim condition shows `Moderate` when you expect `Good`, check whether
  the buoy is currently reporting wave data — `Moderate` means the tide is
  right but no wave height is available yet. This typically clears once the
  first hourly fetch completes.
