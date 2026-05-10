"""DataUpdateCoordinator for the Met Éireann Irish Sea Buoy integration."""
from __future__ import annotations

import asyncio
import csv
import logging
from datetime import timedelta
from io import StringIO

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

try:
    from .const import BASE_URL, DEFAULT_UPDATE_INTERVAL, DOMAIN
except ImportError:
    from const import BASE_URL, DEFAULT_UPDATE_INTERVAL, DOMAIN  # type: ignore[no-redef]

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

        return self._parse_csv(raw_text)

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
            rows = [
                {k.strip(): v.strip() for k, v in row.items() if k is not None}
                for row in reader
                if any(v.strip() for v in row.values() if v is not None)
            ]
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Failed to parse CSV for buoy {self.buoy_id}: {err}") from err

        if not rows:
            raise UpdateFailed(f"No data rows found in CSV for buoy {self.buoy_id}")

        latest = rows[-1]  # most-recent reading is the last row
        _LOGGER.debug("Buoy %s latest reading: %s", self.buoy_id, latest)
        return latest
