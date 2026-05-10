"""
Tests for tides.py — tidal harmonic prediction engine.

Covers:
  - Port data completeness
  - Equilibrium argument (V0) sanity at J2000.0
  - Height computation (range, variation, cross-port ordering)
  - find_extrema (count, alternation, spacing, deduplication)
  - state() (key completeness, value ranges, Rising/Falling logic)
  - forecast_curve (point count, time span, value range)
  - upcoming_highs / upcoming_lows (count, ordering, no duplicates)
"""
import math
from datetime import datetime, timedelta, timezone

import pytest

from tides import (
    PORTS,
    TidalExtremum,
    TidalPredictor,
    _V0,
    _SPEEDS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def predictor(port_key: str = "dublin") -> TidalPredictor:
    return TidalPredictor(PORTS[port_key])


REF = datetime(2026, 5, 9, 6, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Port data
# ---------------------------------------------------------------------------

class TestPortData:
    REQUIRED_CONSTITUENTS = {"M2", "S2", "N2", "K1", "O1"}

    def test_all_ports_present(self):
        assert set(PORTS.keys()) == {
            "dublin", "dun_laoghaire", "cork", "galway", "westport", "sligo"
        }

    @pytest.mark.parametrize("port_key", list(PORTS.keys()))
    def test_all_constituents_present(self, port_key):
        missing = self.REQUIRED_CONSTITUENTS - PORTS[port_key].constituents.keys()
        assert not missing, f"{port_key} missing constituents: {missing}"

    @pytest.mark.parametrize("port_key", list(PORTS.keys()))
    def test_amplitudes_positive(self, port_key):
        for name, c in PORTS[port_key].constituents.items():
            assert c.H > 0, f"{port_key}/{name}: amplitude must be positive"

    @pytest.mark.parametrize("port_key", list(PORTS.keys()))
    def test_phase_lags_in_range(self, port_key):
        for name, c in PORTS[port_key].constituents.items():
            assert 0 <= c.g <= 360, f"{port_key}/{name}: phase lag out of range"

    @pytest.mark.parametrize("port_key", list(PORTS.keys()))
    def test_z0_positive(self, port_key):
        assert PORTS[port_key].z0 > 0

    @pytest.mark.parametrize("port_key", list(PORTS.keys()))
    def test_mhws_greater_than_mlws(self, port_key):
        p = PORTS[port_key]
        assert p.mhws > p.mlws


# ---------------------------------------------------------------------------
# Equilibrium arguments (V0)
# ---------------------------------------------------------------------------

class TestEquilibriumArguments:
    def test_v0_keys(self):
        assert set(_V0.keys()) == {"M2", "S2", "N2", "K1", "O1"}

    def test_v0_in_range(self):
        for name, v in _V0.items():
            assert 0 <= v < 360, f"V0[{name}] = {v} out of [0, 360)"

    def test_v0_m2_approx(self):
        """M2 V0 at J2000.0 should be ~124.3° from first-principles calculation."""
        assert abs(_V0["M2"] - 124.3) < 1.0

    def test_v0_s2_approx(self):
        """S2 V0 at J2000.0 should be ~0° (purely solar reference)."""
        assert _V0["S2"] < 1.0 or _V0["S2"] > 359.0

    def test_speeds_semidiurnal_faster_than_diurnal(self):
        assert _SPEEDS["M2"] > _SPEEDS["K1"]
        assert _SPEEDS["S2"] > _SPEEDS["O1"]


# ---------------------------------------------------------------------------
# Height computation
# ---------------------------------------------------------------------------

class TestHeight:
    def test_returns_float(self):
        h = predictor().height(REF)
        assert isinstance(h, float)

    @pytest.mark.parametrize("port_key", list(PORTS.keys()))
    def test_height_within_physical_range(self, port_key):
        """Heights should stay within [-0.5, 8] m for all Irish ports."""
        p = TidalPredictor(PORTS[port_key])
        for offset_h in range(0, 25, 3):
            h = p.height(REF + timedelta(hours=offset_h))
            assert -0.5 <= h <= 8.0, f"{port_key}: height {h} m out of physical range"

    def test_height_varies_over_12_hours(self):
        """Tidal height should not be constant — must vary by at least 1 m over 12 h."""
        p = predictor()
        heights = [p.height(REF + timedelta(hours=i)) for i in range(13)]
        assert (max(heights) - min(heights)) >= 1.0

    def test_galway_range_exceeds_dublin(self):
        """Galway has a larger tidal range than Dublin."""
        p_dub = predictor("dublin")
        p_gal = predictor("galway")
        heights_dub = [p_dub.height(REF + timedelta(hours=i)) for i in range(13)]
        heights_gal = [p_gal.height(REF + timedelta(hours=i)) for i in range(13)]
        range_dub = max(heights_dub) - min(heights_dub)
        range_gal = max(heights_gal) - min(heights_gal)
        assert range_gal > range_dub

    def test_height_rounded_to_3dp(self):
        h = predictor().height(REF)
        assert h == round(h, 3)


# ---------------------------------------------------------------------------
# find_extrema
# ---------------------------------------------------------------------------

class TestFindExtrema:
    def test_returns_requested_count(self):
        extrema = predictor().find_extrema(REF, count=6)
        assert len(extrema) == 6

    def test_alternates_high_low(self):
        extrema = predictor().find_extrema(REF, count=8)
        for i in range(len(extrema) - 1):
            assert extrema[i].kind != extrema[i + 1].kind, (
                f"Consecutive {extrema[i].kind} tides at index {i}"
            )

    def test_extrema_after_from_dt(self):
        extrema = predictor().find_extrema(REF, count=4)
        for ex in extrema:
            assert ex.time >= REF

    def test_spacing_within_m2_range(self):
        """Half-cycle spacing should be 5.5–7.0 h (M2 ± spring/neap modulation)."""
        extrema = predictor().find_extrema(REF, count=8)
        for i in range(len(extrema) - 1):
            gap_h = (extrema[i + 1].time - extrema[i].time).total_seconds() / 3600
            assert 5.5 < gap_h < 7.0, f"Gap {gap_h:.2f} h at index {i} is outside 5.5–7.0 h"

    def test_highs_above_lows(self):
        extrema = predictor().find_extrema(REF, count=8)
        highs = [e.height for e in extrema if e.kind == "high"]
        lows  = [e.height for e in extrema if e.kind == "low"]
        assert min(highs) > max(lows), "Every high should be above every low in the same window"

    def test_no_duplicate_times(self):
        extrema = predictor().find_extrema(REF, count=12)
        times = [e.time for e in extrema]
        assert len(times) == len(set(times)), "Duplicate extremum times found"

    def test_large_count_covers_three_days(self):
        extrema = predictor().find_extrema(REF, count=12)
        highs = [e for e in extrema if e.kind == "high"]
        span_days = (highs[-1].time - highs[0].time).total_seconds() / 86400
        assert span_days >= 2.5, f"Only {span_days:.1f} days covered with count=12"

    def test_height_rounded_to_2dp(self):
        extrema = predictor().find_extrema(REF, count=4)
        for ex in extrema:
            assert ex.height == round(ex.height, 2)


# ---------------------------------------------------------------------------
# state()
# ---------------------------------------------------------------------------

class TestState:
    REQUIRED_KEYS = {
        "height", "state", "next_high_time", "next_high_height",
        "next_low_time", "next_low_height", "minutes_to_high", "minutes_to_low",
        "minutes_since_high", "forecast", "upcoming_highs", "upcoming_lows",
        "port", "mhws", "mlws",
    }

    @pytest.fixture
    def state(self):
        return predictor().state(REF)

    def test_all_keys_present(self, state):
        missing = self.REQUIRED_KEYS - state.keys()
        assert not missing, f"Missing keys: {missing}"

    def test_height_is_float(self, state):
        assert isinstance(state["height"], float)

    def test_state_is_rising_or_falling(self, state):
        assert state["state"] in ("Rising", "Falling")

    def test_minutes_to_high_positive(self, state):
        assert state["minutes_to_high"] > 0

    def test_minutes_to_low_positive(self, state):
        assert state["minutes_to_low"] > 0

    def test_minutes_since_high_non_negative(self, state):
        assert state["minutes_since_high"] is not None
        assert state["minutes_since_high"] >= 0

    def test_next_high_time_is_datetime(self, state):
        assert isinstance(state["next_high_time"], datetime)

    def test_next_high_time_after_ref(self, state):
        assert state["next_high_time"] > REF

    def test_next_low_time_after_ref(self, state):
        assert state["next_low_time"] > REF

    def test_next_high_height_plausible(self, state):
        assert 2.5 <= state["next_high_height"] <= 5.0

    def test_next_low_height_plausible(self, state):
        assert -0.5 <= state["next_low_height"] <= 2.5

    def test_port_name_string(self, state):
        assert isinstance(state["port"], str) and len(state["port"]) > 0

    def test_rising_just_after_low_tide(self):
        """State should be Rising shortly after a low tide."""
        p = predictor()
        low = p.find_extrema(REF, count=2)[0]  # first extremum from REF
        if low.kind == "low":
            s = p.state(low.time + timedelta(minutes=30))
            assert s["state"] == "Rising"

    def test_falling_just_after_high_tide(self):
        """State should be Falling shortly after a high tide."""
        p = predictor()
        extrema = p.find_extrema(REF, count=4)
        highs = [e for e in extrema if e.kind == "high"]
        s = p.state(highs[0].time + timedelta(minutes=30))
        assert s["state"] == "Falling"

    def test_upcoming_highs_count(self, state):
        assert len(state["upcoming_highs"]) == 6

    def test_upcoming_lows_count(self, state):
        assert len(state["upcoming_lows"]) == 6

    def test_upcoming_highs_ordered(self, state):
        times = [h["time"] for h in state["upcoming_highs"]]
        assert times == sorted(times)

    def test_upcoming_lows_ordered(self, state):
        times = [l["time"] for l in state["upcoming_lows"]]
        assert times == sorted(times)

    def test_upcoming_highs_no_duplicates(self, state):
        times = [h["time"] for h in state["upcoming_highs"]]
        assert len(times) == len(set(times))

    def test_upcoming_highs_heights_plausible(self, state):
        for h in state["upcoming_highs"]:
            assert 2.0 <= h["height"] <= 5.0

    def test_upcoming_lows_heights_plausible(self, state):
        for l in state["upcoming_lows"]:
            assert -0.5 <= l["height"] <= 2.5


# ---------------------------------------------------------------------------
# forecast_curve()
# ---------------------------------------------------------------------------

class TestForecastCurve:
    def test_default_point_count(self):
        """72 hours at 30-min intervals = 145 points (inclusive of endpoints)."""
        curve = predictor().forecast_curve(REF)
        assert len(curve) == 145

    def test_custom_interval(self):
        curve = predictor().forecast_curve(REF, hours=24, interval_minutes=60)
        assert len(curve) == 25  # 24 steps + 1 for start

    def test_first_point_at_from_dt(self):
        curve = predictor().forecast_curve(REF)
        first_t = datetime.fromisoformat(curve[0]["t"])
        assert first_t == REF

    def test_last_point_72h_later(self):
        curve = predictor().forecast_curve(REF)
        last_t = datetime.fromisoformat(curve[-1]["t"])
        expected = REF + timedelta(hours=72)
        assert abs((last_t - expected).total_seconds()) < 60

    def test_points_have_t_and_h(self):
        curve = predictor().forecast_curve(REF)
        for pt in curve[:5]:
            assert "t" in pt and "h" in pt

    def test_heights_within_physical_range(self):
        curve = predictor().forecast_curve(REF)
        for pt in curve:
            assert -0.5 <= pt["h"] <= 8.0

    def test_heights_rounded_to_2dp(self):
        curve = predictor().forecast_curve(REF)
        for pt in curve:
            assert pt["h"] == round(pt["h"], 2)

    def test_curve_contains_variation(self):
        """The curve should span at least 2 m over 72 hours."""
        curve = predictor().forecast_curve(REF)
        heights = [pt["h"] for pt in curve]
        assert max(heights) - min(heights) >= 2.0
