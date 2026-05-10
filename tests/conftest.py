"""Shared fixtures for met_ie_buoy tests."""
import sys
import os
from datetime import datetime, timezone

import pytest

# Make the repo root importable without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Make the tests/ dir first on the path so our homeassistant stub is found
# before any real homeassistant package (which likely isn't installed).
sys.path.insert(0, os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# Reference datetime — a known spring-tide morning
# ---------------------------------------------------------------------------
REF_TIME = datetime(2026, 5, 9, 6, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Sample CSV matching the real Met.ie M2 format (trimmed to 3 rows)
# ---------------------------------------------------------------------------
SAMPLE_CSV = """\
ID,name,wmoID,stationId,time,pressure,windDir,windSpeed,windGust,windGustDir,temp,dewPoint,humidity,period,height,waveDir,seaTemp,reportDate,reportTime,updated_At,created_at
829232,M2,62091,,"7 May 19:00",1012.5,190,30,0,,10.8,7.9,82,3.8,0.8,,10.7,07-05-2026,19:00,"2026-05-07 20:20:53",2026-05-07T19:20:53.000000Z
829236,M2,62091,,"7 May 20:00",1012.7,190,35,0,,10.9,7.9,82,4.0,0.9,,10.4,07-05-2026,20:00,"2026-05-07 21:20:22",2026-05-07T20:20:22.000000Z
829240,M2,62091,,"7 May 21:00",1013.0,195,35,0,,11.1,8.1,82,4.0,1.2,,10.7,07-05-2026,21:00,"2026-05-07 22:20:40",2026-05-07T21:20:40.000000Z
"""

# Same CSV with a comment line at the top (to test comment stripping)
SAMPLE_CSV_WITH_COMMENTS = "# Met Eireann Buoy Data\n# Station: M2\n" + SAMPLE_CSV

# CSV with an empty final row (to test blank-row filtering)
SAMPLE_CSV_TRAILING_BLANK = SAMPLE_CSV + "\n\n"
