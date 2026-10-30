"""Wind-based wave height estimate for the Irish Sea buoy (M2).

This is a *rough* fallback for when the buoy's own wave sensor is stuck or
offline.  It uses the standard deep-water fetch-limited wind-wave relation
(Sverdrup-Munk-Bretschneider / JONSWAP form):

    g·Hs / U²  =  0.0016 · (g·F / U²)^½        (fetch-limited sea)
    g·Hs / U²  <= 0.243                        (fully developed sea)

    Hs  significant wave height (m)      U  wind speed (m/s)
    F   fetch — distance the wind has blown over open water (m)

Inputs are the buoy's own wind speed (km/h) and wind direction (degrees the
wind blows FROM).  The fetch for each direction comes from a per-buoy table of
approximate distances to the nearest upwind coast.

Known limitations (checked against real M2 readings, mean error about 0.4 m):
  * It overshoots when the wind builds quickly, because real waves need time
    to grow (no duration limit is modelled).
  * It undershoots when the wind drops, because swell and old waves persist.
  * Swell generated elsewhere (e.g. a distant storm) is invisible to it.
  * The fetch table is read off a map, not surveyed.
Treat it as a sanity check on the buoy, not a replacement for it.
"""
from __future__ import annotations

import math
from typing import Any, NamedTuple

GRAVITY = 9.81                     # m/s²
GROWTH_COEFFICIENT = 0.0016        # fetch-limited growth constant
FULLY_DEVELOPED_LIMIT = 0.243      # g·Hs/U² for a fully developed sea
SECTOR_DEGREES = 22.5              # 16 compass sectors, N first

# Approximate fetch in km for wind blowing FROM each 22.5° sector centre,
# starting at N (0°) and going clockwise:
#   N, NNE, NE, ENE, E, ESE, SE, SSE, S, SSW, SW, WSW, W, WNW, NW, NNW
#
# M2 sits in the western Irish Sea (about 53.5°N 5.4°W).  Westerly winds come
# off the Irish coast only ~50 km away, while southerlies run the length of
# St George's Channel.
FETCH_KM_BY_BUOY: dict[str, tuple[float, ...]] = {
    "M2": (100, 80, 90, 100, 60, 80, 100, 150, 175, 140, 60, 45, 50, 50, 55, 70),
}

_BLANK_VALUES = {"", "NaN", "N/A", "null", "NULL"}


class WaveEstimate(NamedTuple):
    """Result of a wind-based wave height estimate."""
    height_m: float          # estimated significant wave height, rounded to 0.1 m
    fetch_km: float          # fetch used for this wind direction
    wind_speed_kmh: float
    wind_dir_deg: float      # direction the wind blows FROM, normalised to [0, 360)


def parse_number(value: Any) -> float | None:
    """Convert a CSV cell or number to a finite float, or None if unusable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if value in _BLANK_VALUES:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def supports_buoy(buoy_id: str) -> bool:
    """True if a fetch table exists for this buoy (wave estimates are M2-only)."""
    return str(buoy_id).upper() in FETCH_KM_BY_BUOY


def fetch_km(buoy_id: str, wind_dir_deg: float) -> float | None:
    """Fetch (km) for wind from *wind_dir_deg*, interpolated between sectors."""
    table = FETCH_KM_BY_BUOY.get(str(buoy_id).upper())
    if table is None:
        return None
    position = (wind_dir_deg % 360.0) / SECTOR_DEGREES
    lower = int(position) % len(table)
    upper = (lower + 1) % len(table)
    fraction = position - int(position)
    return table[lower] * (1.0 - fraction) + table[upper] * fraction


def estimate_height_m(wind_speed_kmh: float, fetch_km_value: float) -> float:
    """Unrounded fetch-limited significant wave height (m)."""
    wind = wind_speed_kmh / 3.6   # km/h -> m/s
    if wind <= 0 or fetch_km_value <= 0:
        return 0.0
    fetch_m = fetch_km_value * 1000.0
    dimensionless = GROWTH_COEFFICIENT * math.sqrt(GRAVITY * fetch_m / wind**2)
    dimensionless = min(dimensionless, FULLY_DEVELOPED_LIMIT)
    return dimensionless * wind**2 / GRAVITY


def estimate_for_buoy(
    buoy_id: str, wind_speed_kmh: Any, wind_dir_deg: Any
) -> WaveEstimate | None:
    """Estimate wave height from wind, or None if the inputs can't support one.

    Returns None for an unsupported buoy, a missing/non-numeric/negative wind
    speed, or a missing/non-numeric wind direction.
    """
    if not supports_buoy(buoy_id):
        return None
    speed = parse_number(wind_speed_kmh)
    direction = parse_number(wind_dir_deg)
    if speed is None or direction is None or speed < 0:
        return None

    direction = direction % 360.0
    fetch = fetch_km(buoy_id, direction)
    if fetch is None:
        return None
    return WaveEstimate(
        height_m=round(estimate_height_m(speed, fetch), 1),
        fetch_km=round(fetch, 1),
        wind_speed_kmh=speed,
        wind_dir_deg=direction,
    )


def estimate_from_row(buoy_id: str, row: dict[str, str]) -> WaveEstimate | None:
    """Estimate wave height from a buoy CSV row (uses windSpeed and windDir)."""
    return estimate_for_buoy(buoy_id, row.get("windSpeed"), row.get("windDir"))
