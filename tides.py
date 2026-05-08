"""
Tidal harmonic prediction for Irish ports.

Model : 5 constituents — M2, S2, N2, K1, O1
Source: Admiralty Tide Tables Vol 1 (NW European Waters)
Accuracy: ±15 cm height, ±10 min timing (typical)

Theory:
  h(t) = Z0 + Σ Hₙ · cos(ωₙ·T + V0ₙ − gₙ)

  where T    = hours since J2000.0 (2000-01-01 12:00 UTC)
        V0ₙ  = equilibrium argument at J2000.0 (degrees)
        ωₙ   = angular speed (degrees/hour)
        Hₙ   = amplitude (m) from Admiralty Tide Tables
        gₙ   = phase lag (degrees) from Admiralty Tide Tables

Equilibrium arguments derived from GMST and mean lunar/solar longitudes
following Schureman (1940) "Manual of Harmonic Analysis and Prediction of
Tides", US Coast and Geodetic Survey Special Publication No. 98.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Reference epoch and astronomical rates
# ---------------------------------------------------------------------------

_J2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

# All quantities in degrees or degrees/hour
_GMST_J2000 = 280.46061837   # Greenwich Mean Sidereal Time at J2000.0
_s_J2000    = 218.3165       # Moon's mean longitude
_h_J2000    = 280.4665       # Sun's mean longitude
_p_J2000    =  83.3535       # Moon's mean longitude of perigee

_GMST_RATE  =  15.04106864   # GMST rate (°/h) — sidereal day
_s_RATE     =   0.54901655   # Moon's mean longitude rate
_h_RATE     =   0.04106864   # Sun's mean longitude rate
_p_RATE     =   0.00464183   # Moon's perigee longitude rate

# Constituent angular speeds (degrees / mean solar hour)
_SPEEDS: dict[str, float] = {
    "M2": 28.9841042,   # Principal lunar semidiurnal  (~12.42 h)
    "S2": 30.0000000,   # Principal solar semidiurnal  (~12.00 h)
    "N2": 28.4397295,   # Larger lunar elliptic semi.  (~12.66 h)
    "K1": 15.0410686,   # Luni-solar declinational diurnal (~23.93 h)
    "O1": 13.9430356,   # Principal lunar diurnal      (~25.82 h)
}


def _v0_at_j2000() -> dict[str, float]:
    """
    Equilibrium arguments at J2000.0 (degrees), derived analytically.

    Formulae:
      V_M2 = 2·GMST − 2s           (speed = 2·15.0411 − 2·0.5490 = 28.9841 ✓)
      V_S2 = 2·GMST − 2h           (speed = 2·15.0411 − 2·0.0411 = 30.0000 ✓)
      V_N2 = 2·GMST − 3s + p       (speed = 28.4397 ✓)
      V_K1 = GMST + 90°             (speed = 15.0411 ✓)
      V_O1 = GMST − 2s + 270°      (speed = 15.0411 − 1.0980 = 13.9431 ✓)
    """
    g = _GMST_J2000
    s = _s_J2000
    h = _h_J2000
    p = _p_J2000
    return {
        "M2": (2 * g - 2 * s)       % 360,   # ≈ 124.3°
        "S2": (2 * g - 2 * h)       % 360,   # ≈   0.0°
        "N2": (2 * g - 3 * s + p)   % 360,   # ≈ 349.3°
        "K1": (g + 90.0)            % 360,   # ≈  10.5°
        "O1": (g - 2 * s + 270.0)   % 360,   # ≈ 113.8°
    }


_V0 = _v0_at_j2000()   # computed once at import time


# ---------------------------------------------------------------------------
# Port data
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Constituent:
    """Amplitude (m) and phase lag (°) from Admiralty Tide Tables."""
    H: float   # amplitude in metres
    g: float   # phase lag in degrees


@dataclass(frozen=True)
class TidePort:
    """Harmonic constants for one tidal prediction reference port."""
    name: str
    lat: float
    lon: float
    z0: float           # Mean Sea Level above Chart Datum (m)
    mhws: float         # Mean High Water Springs (m CD)
    mlws: float         # Mean Low Water Springs (m CD)
    constituents: dict[str, Constituent]


# Admiralty Tide Tables Vol 1 — selected Irish reference ports
# Phase lags (g) are Greenwich epochs in degrees.
PORTS: dict[str, TidePort] = {
    "dublin": TidePort(
        name="Dublin Port",
        lat=53.342, lon=-6.229,
        z0=2.03, mhws=4.1, mlws=0.7,
        constituents={
            "M2": Constituent(H=1.866, g=326.0),
            "S2": Constituent(H=0.573, g=356.0),
            "N2": Constituent(H=0.394, g=302.0),
            "K1": Constituent(H=0.074, g= 51.0),
            "O1": Constituent(H=0.067, g= 21.0),
        },
    ),
    "dun_laoghaire": TidePort(
        name="Dún Laoghaire",
        lat=53.302, lon=-6.133,
        z0=2.05, mhws=4.1, mlws=0.7,
        constituents={
            "M2": Constituent(H=1.870, g=326.0),
            "S2": Constituent(H=0.575, g=356.0),
            "N2": Constituent(H=0.395, g=302.0),
            "K1": Constituent(H=0.075, g= 51.0),
            "O1": Constituent(H=0.068, g= 21.0),
        },
    ),
    "cork": TidePort(
        name="Cork Harbour (Cobh)",
        lat=51.851, lon=-8.295,
        z0=2.08, mhws=4.2, mlws=0.8,
        constituents={
            "M2": Constituent(H=1.760, g=285.0),
            "S2": Constituent(H=0.570, g=316.0),
            "N2": Constituent(H=0.340, g=263.0),
            "K1": Constituent(H=0.080, g=352.0),
            "O1": Constituent(H=0.060, g=311.0),
        },
    ),
    "galway": TidePort(
        name="Galway",
        lat=53.272, lon=-9.048,
        z0=2.66, mhws=5.0, mlws=0.8,
        constituents={
            "M2": Constituent(H=2.060, g=295.0),
            "S2": Constituent(H=0.610, g=323.0),
            "N2": Constituent(H=0.400, g=273.0),
            "K1": Constituent(H=0.090, g= 27.0),
            "O1": Constituent(H=0.080, g=354.0),
        },
    ),
    "westport": TidePort(
        name="Westport",
        lat=53.802, lon=-9.516,
        z0=3.28, mhws=6.2, mlws=1.4,
        constituents={
            "M2": Constituent(H=2.400, g=314.0),
            "S2": Constituent(H=0.700, g=341.0),
            "N2": Constituent(H=0.470, g=292.0),
            "K1": Constituent(H=0.120, g= 62.0),
            "O1": Constituent(H=0.100, g= 26.0),
        },
    ),
    "sligo": TidePort(
        name="Sligo",
        lat=54.270, lon=-8.469,
        z0=2.08, mhws=4.0, mlws=0.6,
        constituents={
            "M2": Constituent(H=1.780, g=330.0),
            "S2": Constituent(H=0.540, g=  0.0),
            "N2": Constituent(H=0.340, g=308.0),
            "K1": Constituent(H=0.090, g= 58.0),
            "O1": Constituent(H=0.080, g= 27.0),
        },
    ),
}


# ---------------------------------------------------------------------------
# Tidal extremum
# ---------------------------------------------------------------------------

class TidalExtremum(NamedTuple):
    time: datetime
    height: float   # metres above Chart Datum
    kind: str       # "high" or "low"


# ---------------------------------------------------------------------------
# Predictor
# ---------------------------------------------------------------------------

class TidalPredictor:
    """
    Compute tidal heights and find extrema for a given port.

    Usage:
        predictor = TidalPredictor(PORTS["dublin"])
        now = datetime.now(timezone.utc)
        print(predictor.height(now))          # e.g. 2.47 m
        print(predictor.state(now))           # dict with all info
    """

    def __init__(self, port: TidePort) -> None:
        self._port = port

    # ------------------------------------------------------------------
    # Core height computation
    # ------------------------------------------------------------------

    def height(self, dt: datetime) -> float:
        """Tidal height above Chart Datum (m) at datetime dt (UTC)."""
        dt_utc = dt.astimezone(timezone.utc)
        T = (dt_utc - _J2000).total_seconds() / 3600.0  # hours from J2000.0

        h = self._port.z0
        for name, speed in _SPEEDS.items():
            c = self._port.constituents.get(name)
            if c is None:
                continue
            arg_deg = _V0[name] + speed * T - c.g
            h += c.H * math.cos(math.radians(arg_deg))
        return round(h, 3)

    def _dheight_dt(self, dt: datetime) -> float:
        """Approximate rate of change of height (m/h) at dt."""
        delta = timedelta(minutes=5)
        return (self.height(dt + delta) - self.height(dt - delta)) / (10.0 / 60.0)

    # ------------------------------------------------------------------
    # Extremum finding
    # ------------------------------------------------------------------

    def find_extrema(self, from_dt: datetime, count: int = 6) -> list[TidalExtremum]:
        """
        Return the next `count` tidal extrema after from_dt, alternating
        high / low.  Searches up to ~40 hours ahead (covers >3 M2 cycles).
        """
        from_dt = from_dt.astimezone(timezone.utc)

        # Coarse scan: 10-minute samples over 40 hours
        step = timedelta(minutes=10)
        samples: list[tuple[datetime, float]] = []
        t = from_dt
        for _ in range(241):   # 241 × 10 min ≈ 40 h
            samples.append((t, self.height(t)))
            t += step

        extrema: list[TidalExtremum] = []
        for i in range(1, len(samples) - 1):
            t_prev, h_prev = samples[i - 1]
            t_curr, h_curr = samples[i]
            t_next, h_next = samples[i + 1]

            is_high = (h_curr >= h_prev) and (h_curr >= h_next) and (h_curr > h_prev or h_curr > h_next)
            is_low  = (h_curr <= h_prev) and (h_curr <= h_next) and (h_curr < h_prev or h_curr < h_next)

            if is_high or is_low:
                refined_t = self._refine_extremum(t_prev, t_next, find_max=is_high)
                refined_h = self.height(refined_t)
                kind = "high" if is_high else "low"
                extrema.append(TidalExtremum(refined_t, round(refined_h, 2), kind))
                if len(extrema) >= count:
                    break

        return extrema

    def _refine_extremum(
        self,
        t_lo: datetime,
        t_hi: datetime,
        find_max: bool,
        iterations: int = 24,
    ) -> datetime:
        """Bisect interval to locate an extremum to within ~1 minute."""
        for _ in range(iterations):
            span_s = (t_hi - t_lo).total_seconds()
            if span_s < 60:
                break
            t_mid = t_lo + timedelta(seconds=span_s / 2)
            probe  = timedelta(minutes=1)
            slope = self.height(t_mid + probe) - self.height(t_mid - probe)
            if find_max:
                # Maximum: move left boundary right while slope > 0
                if slope > 0:
                    t_lo = t_mid
                else:
                    t_hi = t_mid
            else:
                # Minimum: move left boundary right while slope < 0
                if slope < 0:
                    t_lo = t_mid
                else:
                    t_hi = t_mid
        return t_lo + (t_hi - t_lo) / 2

    # ------------------------------------------------------------------
    # State summary
    # ------------------------------------------------------------------

    def state(self, dt: datetime) -> dict:
        """
        Return a dict summarising the tidal state at dt.

        Keys:
          height              float  metres above Chart Datum
          state               str    "Rising" | "Falling"
          next_high_time      datetime (UTC) | None
          next_high_height    float | None
          next_low_time       datetime (UTC) | None
          next_low_height     float | None
          minutes_to_high     int | None
          minutes_to_low      int | None
          minutes_since_high  int | None  (minutes since most recent past high)
          port                str    port name
          mhws                float  Mean High Water Springs (m CD)
          mlws                float  Mean Low Water Springs (m CD)
        """
        dt = dt.astimezone(timezone.utc)
        current_height = self.height(dt)
        rising = self._dheight_dt(dt) > 0

        # Search window: start 7 hours back so we always capture the
        # most recent past high as well as upcoming ones.
        extrema = self.find_extrema(dt - timedelta(hours=7), count=8)

        past_high:  TidalExtremum | None = None
        next_high:  TidalExtremum | None = None
        next_low:   TidalExtremum | None = None
        for ex in extrema:
            if ex.time <= dt:
                if ex.kind == "high":
                    past_high = ex   # keep updating — last one wins (most recent)
            else:
                if ex.kind == "high" and next_high is None:
                    next_high = ex
                elif ex.kind == "low" and next_low is None:
                    next_low = ex

        def _mins_to(ex: TidalExtremum | None) -> int | None:
            return None if ex is None else round((ex.time - dt).total_seconds() / 60)

        def _mins_since(ex: TidalExtremum | None) -> int | None:
            return None if ex is None else round((dt - ex.time).total_seconds() / 60)

        return {
            "height":             current_height,
            "state":              "Rising" if rising else "Falling",
            "next_high_time":     next_high.time   if next_high else None,
            "next_high_height":   next_high.height if next_high else None,
            "next_low_time":      next_low.time    if next_low  else None,
            "next_low_height":    next_low.height  if next_low  else None,
            "minutes_to_high":    _mins_to(next_high),
            "minutes_to_low":     _mins_to(next_low),
            "minutes_since_high": _mins_since(past_high),
            "port":               self._port.name,
            "mhws":               self._port.mhws,
            "mlws":               self._port.mlws,
        }
