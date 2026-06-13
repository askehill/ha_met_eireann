# Met Éireann Irish Sea Buoy — Home Assistant Custom Component

Context file for Claude sessions working on this repo.

## What this is

A Home Assistant custom integration (`custom_components/met_ie_buoy/`) that:
- Pulls live buoy observations from Met.ie's public CSV endpoint (M2/M3/M4/M5/M6 buoys) and exposes each CSV column as a sensor.
- Optionally computes tidal predictions locally via harmonic analysis (no API needed) for several Irish ports.
- Optionally provides a "swim condition" sensor combining wave height, tide state, and daylight.
- Includes an ApexCharts Lovelace card config (`apexcharts_tide_card.yaml`) for a 72-hour tide curve.

Repo: `git@github.com:askehill/ha_met_eireann.git`, branch `main`.

## Layout

- `custom_components/met_ie_buoy/__init__.py` — integration setup
- `custom_components/met_ie_buoy/const.py` — constants, sensor metadata
- `custom_components/met_ie_buoy/coordinator.py` — data update coordinator (buoy CSV fetch, soft-failure/caching behaviour)
- `custom_components/met_ie_buoy/sensor.py` — sensor entities (buoy, tide, swim condition) — largest file
- `custom_components/met_ie_buoy/tides.py` — harmonic tide prediction model (Admiralty constants)
- `tests/` — pytest suite with a minimal local `homeassistant` shim (`tests/homeassistant/`) so tests run without a full HA install
- `README.md` — user-facing docs (install, sensors, automations, troubleshooting)

## Running tests

```
pytest
```
(`pytest.ini` + `requirements-test.txt` at repo root configure this.)

## Notes / conventions

- Buoy sensors should soft-fail (keep last known value) on empty/missing CSV data rather than going unavailable; only mark unavailable on actual network/HTTP errors. See `coordinator.py` and `tests/test_coordinator.py`.
- Tide sensors are fully local/offline — only buoy sensors need network access.
- When adding sensors, update `const.py → SENSOR_METADATA` and the README sensor tables.
- Keep README in sync with any new sensors, config options, or behaviour changes.
