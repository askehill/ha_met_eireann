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
- `custom_components/met_ie_buoy/swim.py` — swim condition rules (pure Python; `swim_condition()` is what the sensor calls and what `tests/test_swim.py` tests)
- `custom_components/met_ie_buoy/waves.py` — wind-based wave height estimate (fetch-limited model, M2 fetch table; pure Python, no HA imports)
- `tests/` — pytest suite with a minimal local `homeassistant` shim (`tests/homeassistant/`) so tests run without a full HA install
- `README.md` — user-facing docs (install, sensors, automations, troubleshooting)

## Running tests

```
pytest
```
(`pytest.ini` + `requirements-test.txt` at repo root configure this.)

## Notes / conventions

- Buoy sensors should soft-fail (keep last known value) on empty/missing CSV data rather than going unavailable; only mark unavailable on actual network/HTTP errors. See `coordinator.py` and `tests/test_coordinator.py`.
- Wind speeds in the Met.ie buoy CSV are **km/h** (not knots).
- Stuck-wave-sensor detection lives in `coordinator.py` (`_update_stuck_state`): height AND period identical for `STUCK_VALUE_MIN_ROWS` (6) rows → wave sensors report unknown and the swim sensor ignores wave height. Real fixtures: `tests/fixtures/` (`m2_stuck_wave_oct2026.csv` frozen, `m2_normal_may2026.csv` healthy).
- Estimated Wave Height is M2-only (needs an entry in `waves.FETCH_KM_BY_BUOY`); it is an estimate (~±0.4 m) and never replaces the measured wave height. Tests: `tests/test_waves.py`.
- Swim Condition falls back to the wind-based estimate when the buoy wave height is missing/stuck and appends `*` (`Perfect*`/`Choppy*`/`Rough*`); `Poor`/`Moderate` are never starred. Keep README automation guidance about the asterisk in sync.
- Tide sensors are fully local/offline — only buoy sensors need network access.
- When adding sensors, update `const.py → SENSOR_METADATA` and the README sensor tables.
- Keep README in sync with any new sensors, config options, or behaviour changes.
