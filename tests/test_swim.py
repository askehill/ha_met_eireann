"""
Tests for swim condition logic.

Tests the production swim rules in swim.py (the same function
SwimConditionSensor calls), with no Home Assistant fixture needed.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "met_ie_buoy"))

from const import SWIM_ROUGH_WAVE_THRESHOLD, SWIM_TIDE_WINDOW_MINUTES
from swim import ESTIMATE_MARKER, is_near_high_tide, swim_condition

# swim_condition is the production function (swim.py), used by SwimConditionSensor.


# ---------------------------------------------------------------------------
# Tide window tests
# ---------------------------------------------------------------------------

class TestTideWindow:
    def test_exactly_at_window_boundary_approaching(self):
        assert swim_condition(SWIM_TIDE_WINDOW_MINUTES, None, 0.5) == "Perfect"

    def test_one_minute_inside_window_approaching(self):
        assert swim_condition(SWIM_TIDE_WINDOW_MINUTES - 1, None, 0.5) == "Perfect"

    def test_one_minute_outside_window_approaching(self):
        assert swim_condition(SWIM_TIDE_WINDOW_MINUTES + 1, None, 0.5) == "Poor"

    def test_exactly_at_window_boundary_receding(self):
        assert swim_condition(999, SWIM_TIDE_WINDOW_MINUTES, 0.5) == "Perfect"

    def test_one_minute_inside_window_receding(self):
        assert swim_condition(999, SWIM_TIDE_WINDOW_MINUTES - 1, 0.5) == "Perfect"

    def test_one_minute_outside_window_receding(self):
        assert swim_condition(999, SWIM_TIDE_WINDOW_MINUTES + 1, 0.5) == "Poor"

    def test_at_high_tide_itself(self):
        assert swim_condition(0, 0, 0.5) == "Perfect"

    def test_far_from_high_tide(self):
        assert swim_condition(300, 250, 0.5) == "Poor"

    def test_both_none_means_poor(self):
        assert swim_condition(None, None, 0.5) == "Poor"


# ---------------------------------------------------------------------------
# Wave height tests
# ---------------------------------------------------------------------------

class TestWaveHeight:
    def test_exactly_at_threshold(self):
        assert swim_condition(30, None, 1.0, threshold=1.0) == "Perfect"

    def test_just_below_threshold(self):
        assert swim_condition(30, None, 0.99, threshold=1.0) == "Perfect"

    def test_just_above_threshold(self):
        assert swim_condition(30, None, 1.01, threshold=1.0) == "Choppy"

    def test_exactly_at_rough_threshold(self):
        assert swim_condition(30, None, SWIM_ROUGH_WAVE_THRESHOLD, threshold=1.0) == "Choppy"

    def test_just_above_rough_threshold(self):
        assert swim_condition(30, None, SWIM_ROUGH_WAVE_THRESHOLD + 0.01, threshold=1.0) == "Rough"

    def test_very_rough_seas(self):
        assert swim_condition(30, None, 3.5, threshold=1.0) == "Rough"

    def test_flat_calm(self):
        assert swim_condition(30, None, 0.1, threshold=1.0) == "Perfect"

    def test_custom_threshold(self):
        assert swim_condition(30, None, 1.5, threshold=2.0) == "Perfect"
        assert swim_condition(30, None, 2.1, threshold=2.0, rough_threshold=2.5) == "Choppy"


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
        assert swim_condition(30, None, 0.5, daylight=True) == "Perfect"

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
        assert swim_condition(30, None, 0.5, daylight=True)  == "Perfect"  # all met
        assert swim_condition(30, None, 1.5, daylight=True)  == "Choppy"   # waves choppy
        assert swim_condition(300, None, 0.5, daylight=True) == "Poor"     # tide bad
        assert swim_condition(30, None, 0.5, daylight=False) == "Poor"     # dark

    def test_near_high_tide_rough_seas(self):
        assert swim_condition(10, None, 2.0, daylight=True, threshold=1.0) == "Rough"

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
        assert result == "Perfect"

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


# ---------------------------------------------------------------------------
# Estimated wave height ("*" marker)
# ---------------------------------------------------------------------------

class TestEstimatedWaveMarker:
    """When the wave height is the wind-based estimate, banded states get a '*'."""

    def test_marker_is_an_asterisk(self):
        assert ESTIMATE_MARKER == "*"

    @pytest.mark.parametrize("wave, expected", [
        (0.4, "Perfect*"),
        (1.0, "Perfect*"),      # at the threshold
        (1.01, "Choppy*"),
        (1.75, "Choppy*"),      # at the rough threshold
        (1.76, "Rough*"),
        (2.4, "Rough*"),
    ])
    def test_estimated_states_are_starred(self, wave, expected):
        assert swim_condition(30, None, wave, wave_is_estimate=True) == expected

    @pytest.mark.parametrize("wave, expected", [
        (0.4, "Perfect"), (1.4, "Choppy"), (2.4, "Rough"),
    ])
    def test_measured_states_are_not_starred(self, wave, expected):
        assert swim_condition(30, None, wave, wave_is_estimate=False) == expected

    def test_same_thresholds_apply_to_estimate_and_measurement(self):
        for wave in (0.2, 1.0, 1.2, 1.75, 2.0):
            measured = swim_condition(30, None, wave)
            estimated = swim_condition(30, None, wave, wave_is_estimate=True)
            assert estimated == measured + "*"

    def test_poor_is_never_starred(self):
        # Outside the tide window
        assert swim_condition(300, 250, 0.4, wave_is_estimate=True) == "Poor"
        # After dark
        assert swim_condition(30, None, 0.4, daylight=False, wave_is_estimate=True) == "Poor"

    def test_moderate_is_never_starred(self):
        assert swim_condition(30, None, None, wave_is_estimate=True) == "Moderate"
        assert swim_condition(30, None, None) == "Moderate"

    def test_custom_threshold_with_estimate(self):
        assert swim_condition(30, None, 1.3, threshold=1.5, wave_is_estimate=True) == "Perfect*"
        assert swim_condition(30, None, 1.3, threshold=1.0, wave_is_estimate=True) == "Choppy*"

    def test_marker_applies_on_the_receding_side_of_the_tide(self):
        assert swim_condition(999, 45, 0.5, wave_is_estimate=True) == "Perfect*"

    def test_oct_2026_stuck_buoy_scenario(self):
        """Buoy frozen at 2.7 m, wind estimate 2.4 m: inside the tide window both are Rough."""
        assert swim_condition(30, None, 2.4, wave_is_estimate=True) == "Rough*"

    def test_default_threshold_matches_config_default(self):
        from const import DEFAULT_SWIM_WAVE_THRESHOLD
        assert swim_condition(30, None, DEFAULT_SWIM_WAVE_THRESHOLD) == "Perfect"


class TestIsNearHighTide:
    @pytest.mark.parametrize("to_high, since_high, expected", [
        (SWIM_TIDE_WINDOW_MINUTES, None, True),
        (SWIM_TIDE_WINDOW_MINUTES + 1, None, False),
        (None, SWIM_TIDE_WINDOW_MINUTES, True),
        (None, SWIM_TIDE_WINDOW_MINUTES + 1, False),
        (0, 0, True),
        (None, None, False),
        (500, 45, True),
        (45, 500, True),
    ])
    def test_window(self, to_high, since_high, expected):
        assert is_near_high_tide(to_high, since_high) is expected

    def test_custom_window(self):
        assert is_near_high_tide(30, None, window=30) is True
        assert is_near_high_tide(31, None, window=30) is False
