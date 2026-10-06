"""DataUpdateCoordinator for mos_open_data."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    MosOpenDataApiClientAuthenticationError,
    MosOpenDataApiClientError,
    MosOpenDataApiClientRateLimitError,
)
from .const import DATASET_AIR_QUALITY, DATASET_HOT_WATER

if TYPE_CHECKING:
    from .data import MosOpenDataConfigEntry

_LOGGER = logging.getLogger(__package__)


class MosOpenDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Moscow Open Data API."""

    config_entry: MosOpenDataConfigEntry

    async def _async_update_data(self) -> Any:
        """Update data via library."""
        try:
            address = self.config_entry.data.get("address", "")
            client = self.config_entry.runtime_data.client

            # Fetch both datasets independently so one failure doesn't block the other
            hot_water: list[dict] = []
            air_quality: list[dict] = []

            try:
                hot_water = await client.async_get_hot_water_schedule(address=address)
            except MosOpenDataApiClientAuthenticationError as exception:
                raise ConfigEntryAuthFailed(exception) from exception
            except MosOpenDataApiClientRateLimitError as exception:
                raise UpdateFailed(
                    exception,
                    retry_after=exception.retry_after,
                ) from exception
            except MosOpenDataApiClientError as exception:
                _LOGGER.warning(
                    "Failed to fetch hot water schedule (dataset %s): %s",
                    DATASET_HOT_WATER,
                    exception,
                )

            try:
                air_quality = await client.async_get_air_quality(address=address)
            except MosOpenDataApiClientAuthenticationError as exception:
                raise ConfigEntryAuthFailed(exception) from exception
            except MosOpenDataApiClientRateLimitError as exception:
                raise UpdateFailed(
                    exception,
                    retry_after=exception.retry_after,
                ) from exception
            except MosOpenDataApiClientError as exception:
                _LOGGER.warning(
                    "Failed to fetch air quality data (dataset %s): %s",
                    DATASET_AIR_QUALITY,
                    exception,
                )

            return {
                "hot_water_records": hot_water,
                "air_quality_records": air_quality,
                "current_date": None,
                "address": address,
            }
        except MosOpenDataApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except MosOpenDataApiClientRateLimitError as exception:
            raise UpdateFailed(
                exception,
                retry_after=exception.retry_after,
            ) from exception
        except MosOpenDataApiClientError as exception:
            raise UpdateFailed(exception) from exception
