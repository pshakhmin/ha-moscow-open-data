"""DataUpdateCoordinator for mos_open_data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    MosOpenDataApiClientAuthenticationError,
    MosOpenDataApiClientError,
    MosOpenDataApiClientRateLimitError,
)

if TYPE_CHECKING:
    from .data import MosOpenDataConfigEntry


def _local_now() -> datetime:
    """Return the current time as a timezone-aware local datetime."""
    return datetime.now(tz=UTC).astimezone()


class MosOpenDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Moscow Open Data API."""

    config_entry: MosOpenDataConfigEntry

    async def _async_update_data(self) -> Any:
        """Update data via library."""
        try:
            address = self.config_entry.data.get("address", "")
            client = self.config_entry.runtime_data.client

            hot_water = await client.async_get_hot_water_schedule(address=address)
        except MosOpenDataApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except MosOpenDataApiClientRateLimitError as exception:
            raise UpdateFailed(
                exception,
                retry_after=exception.retry_after,
            ) from exception
        except MosOpenDataApiClientError as exception:
            raise UpdateFailed(exception) from exception
        else:
            return {
                "hot_water_records": hot_water,
                "current_date": _local_now(),
                "address": address,
            }
