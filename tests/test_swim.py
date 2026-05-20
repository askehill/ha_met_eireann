"""
Tests for swim condition logic.

The core logic from SwimConditionSensor is extracted here as a standalone
function so it can be tested without a Home Assistant fixture.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "met_ie_buoy"))

from const import SWIM_TIDE_WINDOW_MINUTES

# ---------------------------------------------------------------------------
# Standalone swim condition function (mirrors SwimConditionSensor.native_value)
# ---------------------------------------------------------------------------

def swim_condition(
    minutes_to_high: int | None,
    minutes_since_high: int | None,
    wave_height: float | None,
    daylight: bool = True,
    threshold: float = 1.0,
    window: int = SWIM_TIDE_WINDOW_MINUTES,
) -> str:
    """Return 'Good', 'Moderate', or 'Poor' given tide, wave, and daylight inputs."""
    near = (
        (minutes_to_high   is not None and minutes_to_high   <= window) or
        (minutes_since_high is not None and minutes_since_high <= window)
    )
    if daylight and near and wave_height is not None and wave_height <= threshold:
        return "Good"
    if daylight and near and wave_height is None:
        return "Moderate"
    return "Poor"


# ---------------------------------------------------------------------------
# Tide window tests
# ---------------------------------------------------------------------------

class TestTideWindow:
    def test_exactly_at_window_boundary_approaching(self):
        assert swim_condition(SWIM_TIDE_WINDOW_MINUTES, None, 0.5) == "Good"

    def test_one_minute_inside_window_approaching(self):
        assert swim_condition(SWIM_TIDE_WINDOW_MINUTES - 1, None, 0.5) == "Good"

    def test_one_minute_outside_window_approaching(self):
        assert swim_condition(SWIM_TIDE_WINDOW_MINUTES + 1, None, 0.5) == "Poor"

    def test_exactly_at_window_boundary_receding(self):
        assert swim_condition(999, SWIM_TIDE_WINDOW_MINUTES, 0.5) == "Good"

    def test_one_minute_inside_window_receding(self):
        assert swim_condition(999, SWIM_TIDE_WINDOW_MINUTES - 1, 0.5) == "Good"

    def test_one_minute_outside_window_receding(self):
        assert swim_condition(999, SWIM_TIDE_WINDOW_MINUTES + 1, 0.5) == "Poor"

    def test_at_high_tide_itself(self):
        assert swim_condition(0, 0, 0.5) == "Good"

    def test_far_from_high_tide(self):
        assert swim_condition(300, 250, 0.5) == "Poor"

    def test_both_none_means_poor(self):
        assert swim_condition(None, None, 0.5) == "Poor"


# ---------------------------------------------------------------------------
# Wave height tests
# ---------------------------------------------------------------------------

class TestWaveHeight:
    def test_exactly_at_threshold(self):
        assert swim_condition(30, None, 1.0, threshold=1.0) == "Good"

    def test_just_below_threshold(self):
        assert swim_condition(30, None, 0.99, threshold=1.0) == "Good"

    def test_just_above_threshold(self):
        assert swim_condition(30, None, 1.01, threshold=1.0) == "Poor"

    def test_very_rough_seas(self):
        assert swim_condition(30, None, 3.5, threshold=1.0) == "Poor"

    def test_flat_calm(self):
        assert swim_condition(30, None, 0.1, threshold=1.0) == "Good"

    def test_custom_threshold(self):
        assert swim_condition(30, None, 1.5, threshold=2.0) == "Good"
        assert swim_condition(30, None, 2.1, threshold=2.0) == "Poor"


# ---------------------------------------------------------------------------
# Daylight tests
# ---------------------------------------------------------------------------

class TestDaylight:
    def test_good_requires_daylight(self):
        """All conditions met but no daylight → Poor."""
        assert swim_condition(30, None, 0.5, daylight=False) == "Poor"

    def test_moderate_requires_daylight(self):
        """Tide ok, wave unknown, but no daylight → Poor not Moderate."""
        assert swim_condition(30, None, None, daylight=False) == "Poor"

    def test_good_with_daylight(self):
        assert swim_condition(30, None, 0.5, daylight=True) == "Good"

    def test_night_rough_seas_is_poor(self):
        assert swim_condition(30, None, 2.0, daylight=False) == "Poor"

    def test_night_wrong_tide_is_poor(self):
        assert swim_condition(300, None, 0.5, daylight=False) == "Poor"


# ---------------------------------------------------------------------------
# Moderate state tests
# ---------------------------------------------------------------------------

class TestModerate:
    def test_moderate_when_daylight_tide_ok_wave_unknown(self):
        assert swim_condition(30, None, None, daylight=True) == "Moderate"

    def test_moderate_at_high_tide_wave_unknown(self):
        assert swim_condition(0, 0, None, daylight=True) == "Moderate"

    def test_not_moderate_when_tide_wrong(self):
        """Wave unknown but tide is wrong → Poor, not Moderate."""
        assert swim_condition(300, 250, None, daylight=True) == "Poor"

    def test_not_moderate_at_night(self):
        """Tide ok, wave unknown, but nighttime → Poor."""
        assert swim_condition(30, None, None, daylight=False) == "Poor"


# ---------------------------------------------------------------------------
# Combined conditions
# ---------------------------------------------------------------------------

class TestCombinedConditions:
    def test_good_requires_all_three(self):
        assert swim_condition(30, None, 0.5, daylight=True)  == "Good"    # all met
        assert swim_condition(30, None, 1.5, daylight=True)  == "Poor"    # waves bad
        assert swim_condition(300, None, 0.5, daylight=True) == "Poor"    # tide bad
        assert swim_condition(30, None, 0.5, daylight=False) == "Poor"    # dark

    def test_near_high_tide_rough_seas(self):
        assert swim_condition(10, None, 2.0, daylight=True, threshold=1.0) == "Poor"

    def test_calm_seas_wrong_tide(self):
        assert swim_condition(200, 200, 0.2, daylight=True) == "Poor"


# ---------------------------------------------------------------------------
# Integration with tidal predictor
# ---------------------------------------------------------------------------

class TestSwimWithRealTides:
    """Verify swim logic integrates correctly with live tidal state."""

    def test_good_condition_near_real_high_tide(self):
        from datetime import datetime, timedelta, timezone
        from tides import PORTS, TidalPredictor
        from conftest import REF_TIME

        p = TidalPredictor(PORTS["dublin"])
        extrema = p.find_extrema(REF_TIME, count=4)
        high = next(e for e in extrema if e.kind == "high")
        test_time = high.time - timedelta(minutes=30)

        state = p.state(test_time)
        result = swim_condition(
            state["minutes_to_high"],
            state["minutes_since_high"],
            wave_height=0.4,
            daylight=True,
        )
        assert result == "Good"

    def test_poor_condition_at_low_tide(self):
        from datetime import datetime, timedelta, timezone
        from tides import PORTS, TidalPredictor
        from conftest import REF_TIME

        p = TidalPredictor(PORTS["dublin"])
        extrema = p.find_extrema(REF_TIME, count=4)
        low = next(e for e in extrema if e.kind == "low")
        state = p.state(low.time)
        result = swim_condition(
            state["minutes_to_high"],
            state["minutes_since_high"],
            wave_height=0.4,
            daylight=True,
        )
        assert result == "Poor"

    def test_moderate_near_high_tide_no_wave_data(self):
        from datetime import timedelta
        from tides import PORTS, TidalPredictor
        from conftest import REF_TIME

        p = TidalPredictor(PORTS["dublin"])
        extrema = p.find_extrema(REF_TIME, count=4)
        high = next(e for e in extrema if e.kind == "high")
        test_time = high.time - timedelta(minutes=30)

        state = p.state(test_time)
        result = swim_condition(
            state["minutes_to_high"],
            state["minutes_since_high"],
            wave_height=None,   # buoy data unavailable
            daylight=True,
        )
        assert result == "Moderate"
