"""DataUpdateCoordinator for the Met Éireann Irish Sea Buoy integration."""
from __future__ import annotations

import asyncio
import csv
import logging
from datetime import datetime, timedelta, timezone
from io import StringIO

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

try:
    from .const import (
        BASE_URL,
        DEFAULT_UPDATE_INTERVAL,
        DOMAIN,
        STUCK_CHECK_COLUMNS,
        STUCK_VALUE_MIN_ROWS,
    )
except ImportError:
    from const import (  # type: ignore[no-redef]
        BASE_URL,
        DEFAULT_UPDATE_INTERVAL,
        DOMAIN,
        STUCK_CHECK_COLUMNS,
        STUCK_VALUE_MIN_ROWS,
    )

_LOGGER = logging.getLogger(__name__)


class MetIeBuoyCoordinator(DataUpdateCoordinator[dict[str, str]]):
    """Fetch the latest reading from a Met.ie buoy CSV once per hour."""

    def __init__(
        self,
        hass: HomeAssistant,
        buoy_id: str,
        scan_interval: int = DEFAULT_UPDATE_INTERVAL,
    ) -> None:
        self.buoy_id = buoy_id
        self.url = f"{BASE_URL}{buoy_id}"
        self.last_fetch_time: datetime | None = None  # UTC time of last real data fetch
        # Stuck wave-sensor detection (see _update_stuck_state)
        self.wave_stuck_rows: int = 0                 # length of the identical trailing run
        self.wave_stuck_since: str | None = None      # CSV "time" of the first row in that run

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{buoy_id}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, str]:
        """Pull the CSV and return the most-recent row as a flat dict."""
        session = async_get_clientsession(self.hass)

        try:
            async with asyncio.timeout(30):
                response = await session.get(self.url)
                if response.status != 200:
                    raise UpdateFailed(
                        f"HTTP {response.status} fetching buoy {self.buoy_id} from {self.url}"
                    )
                raw_text = await response.text(encoding="utf-8", errors="replace")
        except asyncio.TimeoutError as err:
            raise UpdateFailed(
                f"Timeout fetching buoy {self.buoy_id}"
            ) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(
                f"Error fetching buoy {self.buoy_id}: {err}"
            ) from err

        result = self._parse_csv(raw_text)
        # Only update last_fetch_time when we got fresh real data — not when
        # we fell back to stale cached data (result is self.data) or got empty {}.
        if result and result is not self.data:
            self.last_fetch_time = datetime.now(timezone.utc)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_csv(self, text: str) -> dict[str, str]:
        """Parse the CSV and return the latest (last) data row as a dict.

        Met.ie CSVs occasionally have comment/metadata lines that start with
        '#' or are otherwise non-data.  We skip those before handing the
        text to csv.DictReader.
        """
        lines = [line for line in text.splitlines() if not line.strip().startswith("#")]
        clean_text = "\n".join(lines)

        try:
            reader = csv.DictReader(StringIO(clean_text))
            # Guard against malformed headers: csv.DictReader uses None as the key
            # for any extra values that overflow the declared columns.  We drop
            # those, strip whitespace from all valid keys/values, and skip rows
            # that are entirely empty or whitespace.
            if reader.fieldnames and all(f is None for f in reader.fieldnames):
                raise UpdateFailed(
                    f"CSV for buoy {self.buoy_id} has no recognisable header row"
                )
            rows = [
                {k.strip(): v.strip() for k, v in row.items() if k is not None}
                for row in reader
                if any(v.strip() for v in row.values() if v is not None)
            ]
        except UpdateFailed:
            raise
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Failed to parse CSV for buoy {self.buoy_id}: {err}") from err

        if not rows:
            if self.data:
                _LOGGER.warning(
                    "Buoy %s returned an empty CSV — keeping last known values until "
                    "the server recovers",
                    self.buoy_id,
                )
                return self.data  # stale-but-valid: sensors keep their last state
            _LOGGER.warning(
                "Buoy %s returned an empty CSV on first fetch — buoy sensors will "
                "show as unknown until data arrives",
                self.buoy_id,
            )
            return {}  # no prior data; don't raise so tide sensors can still load

        self._update_stuck_state(rows)

        latest = rows[-1]  # most-recent reading is the last row
        _LOGGER.debug("Buoy %s latest reading: %s", self.buoy_id, latest)
        return latest

    # ------------------------------------------------------------------
    # Stuck-sensor detection
    # ------------------------------------------------------------------

    @property
    def wave_data_stuck(self) -> bool:
        """True when the buoy's wave sensor appears frozen.

        The wave channel can freeze on the buoy while every other channel
        (wind, pressure, temperature) keeps updating, so the feed still looks
        fresh.  A frozen sensor repeats the same height AND period every hour.
        """
        return self.wave_stuck_rows >= STUCK_VALUE_MIN_ROWS

    def _update_stuck_state(self, rows: list[dict[str, str]]) -> None:
        """Measure how many trailing rows repeat the latest wave values exactly.

        Requires every column in STUCK_CHECK_COLUMNS to be present and non-blank
        in the latest row (so a CSV without both columns is never flagged), then
        counts back through the rows while those values stay identical.
        """
        was_stuck = self.wave_data_stuck
        run = 0
        since: str | None = None

        latest = rows[-1]
        cols = [c for c in STUCK_CHECK_COLUMNS if c in latest]
        if len(cols) == len(STUCK_CHECK_COLUMNS):
            signature = tuple(latest[c] for c in cols)
            if all(v not in ("", "NaN", "N/A", "null", "NULL") for v in signature):
                for row in reversed(rows):
                    if tuple(row.get(c) for c in cols) == signature:
                        run += 1
                        since = row.get("time")
                    else:
                        break

        self.wave_stuck_rows = run
        self.wave_stuck_since = since if self.wave_data_stuck else None

        if self.wave_data_stuck and not was_stuck:
            _LOGGER.warning(
                "Buoy %s wave sensor looks stuck: %s have been identical (%s) for the "
                "last %d readings (since %s). Wave height/period will be reported as "
                "unknown and ignored by the swim sensor until the values change.",
                self.buoy_id,
                "/".join(cols),
                "/".join(latest[c] for c in cols),
                run,
                since,
            )
        elif was_stuck and not self.wave_data_stuck:
            _LOGGER.info(
                "Buoy %s wave sensor is reporting changing values again", self.buoy_id
            )
