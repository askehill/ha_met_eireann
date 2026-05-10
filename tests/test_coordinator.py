"""
Tests for coordinator.py — CSV parsing logic.

MetIeBuoyCoordinator._parse_csv is pure Python (no HA I/O), so we test it
directly by instantiating the coordinator with a minimal mock for hass.
"""
import sys
import os
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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

    def test_all_comment_csv_raises(self, coordinator):
        all_comments = "# line 1\n# line 2\n"
        with pytest.raises(UpdateFailed):
            coordinator._parse_csv(all_comments)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestParseErrors:
    def test_empty_csv_raises_update_failed(self, coordinator):
        with pytest.raises(UpdateFailed):
            coordinator._parse_csv(EMPTY_CSV)

    def test_header_only_csv_raises_update_failed(self, coordinator):
        with pytest.raises(UpdateFailed):
            coordinator._parse_csv(HEADER_ONLY_CSV)

    def test_update_failed_message_contains_buoy_id(self, coordinator):
        try:
            coordinator._parse_csv(EMPTY_CSV)
        except UpdateFailed as e:
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
