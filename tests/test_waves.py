"""
Tests for waves.py — the wind-based wave height estimate.

waves.py is pure Python (no Home Assistant imports), so everything is tested
directly.  The last classes check the model against real M2 CSV fixtures.
"""
import csv
import math
import os
import statistics
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "met_ie_buoy"))
sys.path.insert(0, os.path.dirname(__file__))  # homeassistant stub

from waves import (
    FETCH_KM_BY_BUOY,
    FULLY_DEVELOPED_LIMIT,
    GRAVITY,
    WaveEstimate,
    estimate_for_buoy,
    estimate_from_row,
    estimate_height_m,
    fetch_km,
    parse_number,
    supports_buoy,
)
from coordinator import MetIeBuoyCoordinator
from conftest import SAMPLE_CSV

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
M2_TABLE = FETCH_KM_BY_BUOY["M2"]


def _fixture_text(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


def _fixture_rows(name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(_fixture_text(name).splitlines()))


# ---------------------------------------------------------------------------
# parse_number
# ---------------------------------------------------------------------------

class TestParseNumber:
    @pytest.mark.parametrize("value, expected", [
        (5, 5.0), (5.5, 5.5), ("43", 43.0), (" 12.5 ", 12.5), ("-3", -3.0), ("0", 0.0),
    ])
    def test_valid_values(self, value, expected):
        assert parse_number(value) == expected

    @pytest.mark.parametrize("value", [
        None, "", "   ", "NaN", "N/A", "null", "NULL", "abc", "1,5",
        float("nan"), float("inf"), float("-inf"), True, False, [], {},
    ])
    def test_unusable_values_return_none(self, value):
        assert parse_number(value) is None


# ---------------------------------------------------------------------------
# Fetch table lookup
# ---------------------------------------------------------------------------

class TestFetchLookup:
    def test_table_has_sixteen_sectors(self):
        assert len(M2_TABLE) == 16

    @pytest.mark.parametrize("sector", range(16))
    def test_sector_centres_return_table_values(self, sector):
        assert fetch_km("M2", sector * 22.5) == pytest.approx(M2_TABLE[sector])

    def test_named_directions(self):
        assert fetch_km("M2", 0) == pytest.approx(100)     # N
        assert fetch_km("M2", 180) == pytest.approx(175)   # S: down St George's Channel
        assert fetch_km("M2", 270) == pytest.approx(50)    # W: off the Irish coast

    def test_interpolates_between_sectors(self):
        # Midway between S (180°, 175 km) and SSW (202.5°, 140 km)
        assert fetch_km("M2", 191.25) == pytest.approx((175 + 140) / 2)

    def test_quarter_way_interpolation(self):
        # A quarter of the way from S (175) to SSW (140)
        assert fetch_km("M2", 180 + 22.5 / 4) == pytest.approx(175 * 0.75 + 140 * 0.25)

    def test_wraps_around_north(self):
        # Midway between NNW (337.5°, 70 km) and N (360°/0°, 100 km)
        assert fetch_km("M2", 348.75) == pytest.approx((70 + 100) / 2)

    def test_just_below_360_is_continuous_with_zero(self):
        assert fetch_km("M2", 359.999) == pytest.approx(fetch_km("M2", 0), abs=0.01)

    @pytest.mark.parametrize("direction, same_as", [
        (360, 0), (450, 90), (720 + 45, 45), (-90, 270), (-22.5, 337.5),
    ])
    def test_directions_are_normalised(self, direction, same_as):
        assert fetch_km("M2", direction) == pytest.approx(fetch_km("M2", same_as))

    def test_always_between_table_min_and_max(self):
        for deg in range(0, 361):
            value = fetch_km("M2", deg)
            assert min(M2_TABLE) - 1e-9 <= value <= max(M2_TABLE) + 1e-9

    def test_south_is_the_longest_fetch(self):
        assert fetch_km("M2", 180) == max(fetch_km("M2", d) for d in range(0, 360))

    def test_buoy_id_is_case_insensitive(self):
        assert fetch_km("m2", 180) == fetch_km("M2", 180)

    def test_unknown_buoy_returns_none(self):
        assert fetch_km("M4", 180) is None


class TestSupportsBuoy:
    def test_m2_supported(self):
        assert supports_buoy("M2") is True
        assert supports_buoy("m2") is True

    @pytest.mark.parametrize("buoy", ["M3", "M4", "M5", "M6", "", "XYZ"])
    def test_others_not_supported(self, buoy):
        assert supports_buoy(buoy) is False


# ---------------------------------------------------------------------------
# Core formula
# ---------------------------------------------------------------------------

class TestEstimateHeightFormula:
    def test_matches_hand_calculation(self):
        # 36 km/h = 10 m/s, 100 km fetch:
        #   g·F/U² = 9.81·1e5/100 = 9810 ; sqrt = 99.045
        #   g·Hs/U² = 0.0016 · 99.045 = 0.158472 ; Hs = 0.158472 · 100 / 9.81
        assert estimate_height_m(36, 100) == pytest.approx(1.6155, abs=1e-3)

    def test_zero_wind_gives_zero(self):
        assert estimate_height_m(0, 150) == 0.0

    def test_negative_wind_gives_zero(self):
        assert estimate_height_m(-10, 150) == 0.0

    @pytest.mark.parametrize("fetch", [0, -5])
    def test_no_fetch_gives_zero(self, fetch):
        assert estimate_height_m(40, fetch) == 0.0

    def test_height_increases_with_wind_speed(self):
        heights = [estimate_height_m(w, 100) for w in range(5, 101, 5)]
        assert heights == sorted(heights)
        assert len(set(heights)) == len(heights)

    def test_height_increases_with_fetch(self):
        heights = [estimate_height_m(40, f) for f in (10, 25, 50, 100, 200, 400)]
        assert heights == sorted(heights)
        assert len(set(heights)) == len(heights)

    def test_fetch_limited_height_is_linear_in_wind(self):
        # Hs = 0.0016·sqrt(F/g)·U  while fetch-limited, so doubling U doubles Hs.
        # (40 and 80 km/h over 100 km are both well below the fully-developed cap.)
        assert estimate_height_m(80, 100) == pytest.approx(2 * estimate_height_m(40, 100))

    def test_quadrupling_fetch_doubles_height(self):
        # Hs ∝ sqrt(F) while fetch-limited (60 km/h: 100 km and 400 km are both uncapped)
        assert estimate_height_m(60, 400) == pytest.approx(2 * estimate_height_m(60, 100))

    def test_light_wind_on_a_long_fetch_is_fully_developed(self):
        # At 20 km/h even 100 km is enough to saturate, so more fetch changes nothing
        assert estimate_height_m(20, 100) == pytest.approx(estimate_height_m(20, 400))

    def test_fully_developed_cap(self):
        # Huge fetch + strong wind must saturate at 0.243·U²/g
        wind_kmh = 100.0
        u = wind_kmh / 3.6
        capped = estimate_height_m(wind_kmh, 10_000)
        assert capped == pytest.approx(FULLY_DEVELOPED_LIMIT * u**2 / GRAVITY)

    def test_cap_is_not_applied_when_fetch_limited(self):
        u = 36 / 3.6
        assert estimate_height_m(36, 50) < FULLY_DEVELOPED_LIMIT * u**2 / GRAVITY

    def test_height_never_negative_or_nan(self):
        for wind in (0, 0.1, 1, 10, 50, 200):
            for fetch in (1, 50, 500):
                h = estimate_height_m(wind, fetch)
                assert h >= 0 and math.isfinite(h)


# ---------------------------------------------------------------------------
# estimate_for_buoy
# ---------------------------------------------------------------------------

class TestEstimateForBuoy:
    def test_returns_wave_estimate_with_inputs_echoed(self):
        est = estimate_for_buoy("M2", 43, 160)
        assert isinstance(est, WaveEstimate)
        assert est.wind_speed_kmh == 43
        assert est.wind_dir_deg == 160
        assert est.fetch_km == pytest.approx(152.8, abs=0.1)

    def test_oct_2026_conditions(self):
        """43 km/h from 160° (the conditions when the buoy wave sensor was stuck)."""
        assert estimate_for_buoy("M2", 43, 160).height_m == 2.4

    def test_height_rounded_to_one_decimal(self):
        h = estimate_for_buoy("M2", 37, 123).height_m
        assert h == round(h, 1)

    def test_accepts_csv_strings(self):
        assert estimate_for_buoy("M2", "43", "160") == estimate_for_buoy("M2", 43, 160)

    def test_calm_wind_gives_zero_height(self):
        est = estimate_for_buoy("M2", 0, 180)
        assert est is not None and est.height_m == 0.0

    def test_direction_360_same_as_zero(self):
        assert estimate_for_buoy("M2", 30, 360) == estimate_for_buoy("M2", 30, 0)

    def test_direction_is_normalised(self):
        est = estimate_for_buoy("M2", 30, 450)
        assert est.wind_dir_deg == 90

    def test_southerly_beats_westerly_for_same_wind(self):
        south = estimate_for_buoy("M2", 40, 180).height_m
        west = estimate_for_buoy("M2", 40, 270).height_m
        assert south > west
        # Ratio should track sqrt(fetch ratio) = sqrt(175/50) ≈ 1.87
        assert south / west > 1.8

    def test_stronger_wind_gives_bigger_waves(self):
        assert estimate_for_buoy("M2", 60, 180).height_m > estimate_for_buoy("M2", 30, 180).height_m

    @pytest.mark.parametrize("speed", [None, "", "NaN", "N/A", "abc", float("nan"), float("inf"), -1, "-5"])
    def test_bad_wind_speed_returns_none(self, speed):
        assert estimate_for_buoy("M2", speed, 180) is None

    @pytest.mark.parametrize("direction", [None, "", "NaN", "N/A", "abc", float("nan"), float("inf")])
    def test_bad_wind_direction_returns_none(self, direction):
        assert estimate_for_buoy("M2", 30, direction) is None

    @pytest.mark.parametrize("buoy", ["M3", "M4", "M5", "M6", "", "nope"])
    def test_unsupported_buoy_returns_none(self, buoy):
        assert estimate_for_buoy(buoy, 30, 180) is None


# ---------------------------------------------------------------------------
# estimate_from_row (what the sensor calls)
# ---------------------------------------------------------------------------

class TestEstimateFromRow:
    @pytest.fixture
    def coordinator(self):
        return MetIeBuoyCoordinator(MagicMock(), buoy_id="M2")

    def test_uses_wind_columns_of_parsed_csv_row(self, coordinator):
        row = coordinator._parse_csv(SAMPLE_CSV)   # last row: 35 km/h from 195°
        est = estimate_from_row("M2", row)
        assert est is not None
        assert est.wind_speed_kmh == 35
        assert est.wind_dir_deg == 195
        assert est.height_m == 1.9

    def test_empty_row_returns_none(self):
        assert estimate_from_row("M2", {}) is None

    def test_missing_direction_returns_none(self):
        assert estimate_from_row("M2", {"windSpeed": "30"}) is None

    def test_missing_speed_returns_none(self):
        assert estimate_from_row("M2", {"windDir": "180"}) is None

    def test_blank_cells_return_none(self):
        assert estimate_from_row("M2", {"windSpeed": "", "windDir": ""}) is None

    def test_other_columns_are_ignored(self):
        row = {"windSpeed": "30", "windDir": "180", "height": "9.9", "period": "1.0"}
        assert estimate_from_row("M2", row) == estimate_from_row("M2", {"windSpeed": "30", "windDir": "180"})

    def test_unsupported_buoy_returns_none(self):
        assert estimate_from_row("M4", {"windSpeed": "30", "windDir": "180"}) is None


# ---------------------------------------------------------------------------
# Real data
# ---------------------------------------------------------------------------

class TestAgainstRealMayData:
    """25 hourly M2 readings (7-8 May 2026) with a healthy wave sensor."""

    @pytest.fixture
    def pairs(self):
        rows = _fixture_rows("m2_normal_may2026.csv")
        return [(estimate_from_row("M2", r), float(r["height"])) for r in rows]

    def test_every_row_produces_an_estimate(self, pairs):
        assert len(pairs) == 25
        assert all(est is not None for est, _ in pairs)

    def test_estimates_are_physically_plausible(self, pairs):
        for est, _ in pairs:
            cap = FULLY_DEVELOPED_LIMIT * (est.wind_speed_kmh / 3.6) ** 2 / GRAVITY
            assert 0 <= est.height_m <= cap + 0.05

    def test_mean_error_is_within_documented_accuracy(self, pairs):
        errors = [est.height_m - observed for est, observed in pairs]
        mae = sum(abs(e) for e in errors) / len(errors)
        bias = sum(errors) / len(errors)
        assert mae < 0.5, f"mean absolute error {mae:.2f} m"
        assert abs(bias) < 0.3, f"bias {bias:+.2f} m"

    def test_estimate_tracks_the_buoy(self, pairs):
        """Estimate and real height rise and fall together (Pearson r ~ 0.79 here)."""
        estimates = [est.height_m for est, _ in pairs]
        observed = [obs for _, obs in pairs]
        assert statistics.correlation(estimates, observed) > 0.6

    def test_known_limitation_wave_memory_after_wind_drops(self, pairs):
        """Wind fell to ~2-7 km/h on 8 May but the buoy still read 0.4 m of leftover sea."""
        calm_rows = [(e, o) for e, o in pairs if e.wind_speed_kmh <= 7]
        assert calm_rows
        assert all(e.height_m < o for e, o in calm_rows)


class TestAgainstRealStuckOctoberData:
    """The frozen feed: height 2.7 / period 4.9 for 25 hours while the wind varied."""

    @pytest.fixture
    def rows(self):
        return _fixture_rows("m2_stuck_wave_oct2026.csv")

    def test_estimates_available_for_every_row(self, rows):
        assert all(estimate_from_row("M2", r) is not None for r in rows)

    def test_estimates_stay_in_a_sensible_range(self, rows):
        heights = [estimate_from_row("M2", r).height_m for r in rows]
        assert 1.5 <= min(heights) and max(heights) <= 3.5

    def test_estimate_responds_to_wind_unlike_the_frozen_sensor(self, rows):
        heights = {estimate_from_row("M2", r).height_m for r in rows}
        assert len(heights) > 1                      # varies with the wind
        assert {r["height"] for r in rows} == {"2.7"}  # buoy value never changes

    def test_latest_estimate_close_to_buoy_value_today(self, rows):
        latest = estimate_from_row("M2", rows[-1])
        assert latest.height_m == pytest.approx(2.4, abs=0.1)

    def test_estimate_is_available_while_buoy_wave_data_is_stuck(self):
        coordinator = MetIeBuoyCoordinator(MagicMock(), buoy_id="M2")
        latest = coordinator._parse_csv(_fixture_text("m2_stuck_wave_oct2026.csv"))
        assert coordinator.wave_data_stuck is True
        assert estimate_from_row("M2", latest) is not None
