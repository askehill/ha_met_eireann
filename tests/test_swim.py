"""
Tests for swim condition logic.

The core logic from SwimConditionSensor is extracted here as a standalone
function so it can be tested without a Home Assistant fixture.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from const import SWIM_TIDE_WINDOW_MINUTES

# ---------------------------------------------------------------------------
# Standalone swim condition function (mirrors SwimConditionSensor.native_value)
# ---------------------------------------------------------------------------

def swim_condition(
    minutes_to_high: int | None,
    minutes_since_high: int | None,
    wave_height: float | None,
    threshold: float = 1.0,
    window: int = SWIM_TIDE_WINDOW_MINUTES,
) -> str:
    """Return 'Good', 'Poor', or 'Unknown' given tide and wave inputs."""
    near = (
        (minutes_to_high   is not None and minutes_to_high   <= window) or
        (minutes_since_high is not None and minutes_since_high <= window)
    )
    if wave_height is None:
        return "Unknown"
    return "Good" if (near and wave_height <= threshold) else "Poor"


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
        """minutes_to_high = 0 means we're exactly at high tide."""
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

    def test_unknown_wave_height(self):
        assert swim_condition(30, None, None) == "Unknown"

    def test_unknown_regardless_of_tide(self):
        """Unknown wave height → Unknown even if tide is perfect."""
        assert swim_condition(0, 0, None) == "Unknown"

    def test_custom_threshold(self):
        assert swim_condition(30, None, 1.5, threshold=2.0) == "Good"
        assert swim_condition(30, None, 2.1, threshold=2.0) == "Poor"


# ---------------------------------------------------------------------------
# Combined conditions
# ---------------------------------------------------------------------------

class TestCombinedConditions:
    def test_good_requires_both_conditions(self):
        """Good only when BOTH near high tide AND waves below threshold."""
        assert swim_condition(30, None, 0.5) == "Good"    # both met
        assert swim_condition(30, None, 1.5) == "Poor"    # tide ok, waves bad
        assert swim_condition(300, None, 0.5) == "Poor"   # waves ok, tide bad
        assert swim_condition(300, None, 1.5) == "Poor"   # both bad

    def test_near_high_tide_with_rough_seas(self):
        assert swim_condition(10, None, 2.0, threshold=1.0) == "Poor"

    def test_calm_seas_wrong_tide_time(self):
        assert swim_condition(200, 200, 0.2) == "Poor"


# ---------------------------------------------------------------------------
# Integration with tidal predictor
# ---------------------------------------------------------------------------

class TestSwimWithRealTides:
    """Verify swim logic integrates correctly with live tidal state."""

    def test_good_condition_near_real_high_tide(self):
        from datetime import datetime, timedelta, timezone
        from tides import PORTS, TidalPredictor

        p = TidalPredictor(PORTS["dublin"])
        # Find a real upcoming high tide and sit 30 min before it
        from conftest import REF_TIME
        extrema = p.find_extrema(REF_TIME, count=4)
        high = next(e for e in extrema if e.kind == "high")
        test_time = high.time - timedelta(minutes=30)

        state = p.state(test_time)
        result = swim_condition(
            state["minutes_to_high"],
            state["minutes_since_high"],
            wave_height=0.4,
        )
        assert result == "Good"

    def test_poor_condition_at_low_tide(self):
        from datetime import datetime, timedelta, timezone
        from tides import PORTS, TidalPredictor

        p = TidalPredictor(PORTS["dublin"])
        from conftest import REF_TIME
        extrema = p.find_extrema(REF_TIME, count=4)
        low = next(e for e in extrema if e.kind == "low")
        # Sit right at low tide — should be ~6 hours from high
        state = p.state(low.time)
        result = swim_condition(
            state["minutes_to_high"],
            state["minutes_since_high"],
            wave_height=0.4,
        )
        assert result == "Poor"
