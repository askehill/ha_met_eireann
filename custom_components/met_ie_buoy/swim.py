"""Swim condition rules (pure Python, no Home Assistant imports).

Used by SwimConditionSensor and tested directly in tests/test_swim.py.

States
------
Perfect / Choppy / Rough   daylight, within the tide window, banded by wave height
Moderate                   daylight, within the tide window, but no wave height at all
Poor                       outside the tide window, or after dark

When the wave height used is the wind-based *estimate* (because the buoy's own
reading is stuck or missing) the wave-banded states carry a trailing "*", e.g.
"Perfect*", so it is clear the call rests on an estimate rather than a measurement.
"""
from __future__ import annotations

try:
    from .const import (
        DEFAULT_SWIM_WAVE_THRESHOLD,
        SWIM_ROUGH_WAVE_THRESHOLD,
        SWIM_TIDE_WINDOW_MINUTES,
    )
except ImportError:
    from const import (  # type: ignore[no-redef]
        DEFAULT_SWIM_WAVE_THRESHOLD,
        SWIM_ROUGH_WAVE_THRESHOLD,
        SWIM_TIDE_WINDOW_MINUTES,
    )

ESTIMATE_MARKER = "*"


def is_near_high_tide(
    minutes_to_high: int | None,
    minutes_since_high: int | None,
    window: int = SWIM_TIDE_WINDOW_MINUTES,
) -> bool:
    """True if within *window* minutes of a high tide (approaching or just passed)."""
    approaching = minutes_to_high is not None and minutes_to_high <= window
    just_passed = minutes_since_high is not None and minutes_since_high <= window
    return approaching or just_passed


def swim_condition(
    minutes_to_high: int | None,
    minutes_since_high: int | None,
    wave_height: float | None,
    daylight: bool = True,
    threshold: float = DEFAULT_SWIM_WAVE_THRESHOLD,
    rough_threshold: float = SWIM_ROUGH_WAVE_THRESHOLD,
    window: int = SWIM_TIDE_WINDOW_MINUTES,
    wave_is_estimate: bool = False,
) -> str:
    """Return the swim state for the given tide, wave and daylight inputs.

    *wave_is_estimate* marks the wave height as the wind-based estimate; the
    wave-banded states then get a trailing "*".  "Poor" and "Moderate" never do,
    because neither depends on a wave height that was actually used.
    """
    near = is_near_high_tide(minutes_to_high, minutes_since_high, window)
    if not (daylight and near):
        return "Poor"
    if wave_height is None:
        return "Moderate"

    if wave_height <= threshold:
        state = "Perfect"
    elif wave_height <= rough_threshold:
        state = "Choppy"
    else:
        state = "Rough"
    return state + ESTIMATE_MARKER if wave_is_estimate else state
