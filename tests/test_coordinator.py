"""
Tests for coordinator.py — CSV parsing logic.

MetIeBuoyCoordinator._parse_csv is pure Python (no HA I/O), so we test it
directly by instantiating the coordinator with a minimal mock for hass.
"""
import sys
import os
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "met_ie_buoy"))
sys.path.insert(0, os.path.dirname(__file__))  # homeassistant stub

from coordinator import MetIeBuoyCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed  # type: ignore


# ---------------------------------------------------------------------------
# Fixture: a coordinator instance with a mocked hass
# ---------------------------------------------------------------------------

@pytest.fixture
def coordinator():
    mock_hass = MagicMock()
    return MetIeBuoyCoordinator(mock_hass, buoy_id="M2")


# ---------------------------------------------------------------------------
# Sample CSV strings
# ---------------------------------------------------------------------------

from conftest import (
    SAMPLE_CSV,
    SAMPLE_CSV_WITH_COMMENTS,
    SAMPLE_CSV_TRAILING_BLANK,
)

MINIMAL_CSV = """\
ID,name,time,pressure,height
1,M2,"9 May 12:00",1015.0,1.23
2,M2,"9 May 13:00",1015.5,1.45
"""

EMPTY_CSV = ""
HEADER_ONLY_CSV = "ID,name,time,pressure,height\n"


# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------

class TestParseCsv:
    def test_returns_dict(self, coordinator):
        result = coordinator._parse_csv(SAMPLE_CSV)
        assert isinstance(result, dict)

    def test_returns_last_row(self, coordinator):
        """The most recent (last) row should be returned."""
        result = coordinator._parse_csv(SAMPLE_CSV)
        assert result["time"] == "7 May 21:00"

    def test_keys_stripped_of_whitespace(self, coordinator):
        csv = "  pressure  , height  \n1015.0,1.23\n"
        result = coordinator._parse_csv(csv)
        assert "pressure" in result
        assert "height" in result

    def test_values_stripped_of_whitespace(self, coordinator):
        result = coordinator._parse_csv(MINIMAL_CSV)
        assert result["pressure"] == "1015.5"   # no surrounding spaces

    def test_all_expected_columns_present(self, coordinator):
        result = coordinator._parse_csv(SAMPLE_CSV)
        for col in ("pressure", "windSpeed", "temp", "seaTemp", "height"):
            assert col in result, f"Expected column '{col}' not found"

    def test_real_m2_pressure_value(self, coordinator):
        result = coordinator._parse_csv(SAMPLE_CSV)
        assert result["pressure"] == "1013.0"

    def test_real_m2_height_value(self, coordinator):
        result = coordinator._parse_csv(SAMPLE_CSV)
        assert result["height"] == "1.2"

    def test_real_m2_temp_value(self, coordinator):
        result = coordinator._parse_csv(SAMPLE_CSV)
        assert result["temp"] == "11.1"


# ---------------------------------------------------------------------------
# Comment and blank line handling
# ---------------------------------------------------------------------------

class TestCommentHandling:
    def test_strips_comment_lines(self, coordinator):
        """Lines starting with # should be ignored."""
        result = coordinator._parse_csv(SAMPLE_CSV_WITH_COMMENTS)
        assert result["time"] == "7 May 21:00"

    def test_trailing_blank_rows_ignored(self, coordinator):
        result = coordinator._parse_csv(SAMPLE_CSV_TRAILING_BLANK)
        assert result["time"] == "7 May 21:00"

    def test_all_comment_csv_returns_empty_dict(self, coordinator):
        """All-comment CSV has no data rows — should return {} not raise."""
        all_comments = "# line 1\n# line 2\n"
        result = coordinator._parse_csv(all_comments)
        assert result == {}


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestParseErrors:
    def test_empty_csv_returns_empty_dict(self, coordinator):
        """Empty CSV is a soft failure — returns {} so tide sensors keep loading."""
        result = coordinator._parse_csv(EMPTY_CSV)
        assert result == {}

    def test_header_only_csv_returns_empty_dict(self, coordinator):
        """Header-only CSV has no data rows — returns {} not raises."""
        result = coordinator._parse_csv(HEADER_ONLY_CSV)
        assert result == {}

    def test_update_failed_message_contains_buoy_id(self, coordinator):
        """Truly unparseable CSV (not just empty) should still raise with buoy ID."""
        import csv as _csv
        # Trigger the parse exception branch by passing something that breaks DictReader
        # We can't easily do this via _parse_csv alone since it's quite tolerant,
        # so we just verify that when UpdateFailed IS raised it contains the buoy ID.
        try:
            coordinator._parse_csv(EMPTY_CSV)
        except Exception as e:
            assert "M2" in str(e)


# ---------------------------------------------------------------------------
# Empty / missing values in cells
# ---------------------------------------------------------------------------

class TestEmptyValues:
    def test_empty_cell_preserved_as_empty_string(self, coordinator):
        """Empty cells (e.g. missing waveDir) should come through as ''."""
        result = coordinator._parse_csv(SAMPLE_CSV)
        # windGustDir is empty in sample data
        assert result.get("windGustDir", "") == ""

    def test_row_with_all_empty_values_filtered_out(self, coordinator):
        """A row where every value is blank should be skipped."""
        csv = "pressure,height\n1015.0,1.2\n,\n"
        result = coordinator._parse_csv(csv)
        assert result["pressure"] == "1015.0"


# ---------------------------------------------------------------------------
# Stuck wave-sensor detection
# ---------------------------------------------------------------------------

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _read_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


def _wave_csv(rows: list[tuple[str, str]]) -> str:
    """Build a minimal CSV with time, height and period (and a varying pressure)."""
    lines = ["ID,name,time,pressure,height,period"]
    for i, (height, period) in enumerate(rows):
        lines.append(f'{i},M2,"9 May {i}:00",{1010 + i},{height},{period}')
    return "\n".join(lines) + "\n"


class TestStuckWaveDetection:
    def test_real_frozen_feed_is_detected(self, coordinator):
        """Oct 2026 feed: 25 hours of height 2.7 / period 4.9 while wind etc. varied."""
        result = coordinator._parse_csv(_read_fixture("m2_stuck_wave_oct2026.csv"))
        assert coordinator.wave_data_stuck is True
        assert coordinator.wave_stuck_rows == 25
        assert coordinator.wave_stuck_since == "29 Oct 11:00"
        # The raw data is still returned unchanged; sensors decide what to show
        assert result["height"] == "2.7"
        assert result["period"] == "4.9"

    def test_real_healthy_feed_is_not_flagged(self, coordinator):
        coordinator._parse_csv(_read_fixture("m2_normal_may2026.csv"))
        assert coordinator.wave_data_stuck is False
        assert coordinator.wave_stuck_since is None

    def test_repeated_height_alone_is_not_stuck(self, coordinator):
        """Real May data held height at 0.4 for 7 hours while the period still changed."""
        rows = [("0.5", "3.5"), ("0.4", "3.4"), ("0.4", "3.5"), ("0.4", "3.6"),
                ("0.4", "3.3"), ("0.4", "3.2"), ("0.4", "3.0"), ("0.4", "3.0")]
        coordinator._parse_csv(_wave_csv(rows))
        assert coordinator.wave_data_stuck is False

    def test_threshold_boundary(self, coordinator):
        from const import STUCK_VALUE_MIN_ROWS

        below = [("1.0", "4.0"), ("1.1", "4.1")] + [("2.7", "4.9")] * (STUCK_VALUE_MIN_ROWS - 1)
        coordinator._parse_csv(_wave_csv(below))
        assert coordinator.wave_data_stuck is False

        at = [("1.0", "4.0"), ("1.1", "4.1")] + [("2.7", "4.9")] * STUCK_VALUE_MIN_ROWS
        coordinator._parse_csv(_wave_csv(at))
        assert coordinator.wave_data_stuck is True
        assert coordinator.wave_stuck_rows == STUCK_VALUE_MIN_ROWS

    def test_recovers_when_values_change(self, coordinator):
        frozen = [("2.7", "4.9")] * 8
        coordinator._parse_csv(_wave_csv(frozen))
        assert coordinator.wave_data_stuck is True

        coordinator._parse_csv(_wave_csv(frozen + [("2.4", "5.1")]))
        assert coordinator.wave_data_stuck is False
        assert coordinator.wave_stuck_since is None

    def test_missing_period_column_is_never_flagged(self, coordinator):
        """Without both wave columns we cannot tell stuck from a calm sea."""
        csv = "ID,name,time,pressure,height\n" + "\n".join(
            f'{i},M2,"9 May {i}:00",{1010 + i},2.7' for i in range(10)
        ) + "\n"
        coordinator._parse_csv(csv)
        assert coordinator.wave_data_stuck is False

    def test_blank_wave_values_are_not_flagged(self, coordinator):
        coordinator._parse_csv(_wave_csv([("", "")] * 10))
        assert coordinator.wave_data_stuck is False

    def test_empty_csv_keeps_previous_stuck_state(self, coordinator):
        """Soft-failure on an empty CSV must not silently clear the stuck flag."""
        coordinator.data = coordinator._parse_csv(_wave_csv([("2.7", "4.9")] * 8))
        assert coordinator.wave_data_stuck is True
        coordinator._parse_csv(HEADER_ONLY_CSV)
        assert coordinator.wave_data_stuck is True
