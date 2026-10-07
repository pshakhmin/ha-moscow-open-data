"""DataUpdateCoordinator for mos_open_data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    MosOpenDataApiClientAuthenticationError,
    MosOpenDataApiClientError,
    MosOpenDataApiClientRateLimitError,
)
from .const import DOMAIN
from .heating import async_fetch_rss, merge_heating_state, parse_heating_events

if TYPE_CHECKING:
    from .data import MosOpenDataConfigEntry


def _local_now() -> datetime:
    """Return the current time as a timezone-aware local datetime."""
    return datetime.now(tz=UTC).astimezone()


class MosOpenDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Moscow Open Data API."""

    config_entry: MosOpenDataConfigEntry

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the coordinator and its heating-season store."""
        super().__init__(*args, **kwargs)
        self._heating_store: Store[dict[str, str | None]] | None = None
        self._heating_state: dict[str, str | None] = {"start": None, "end": None}

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
                "heating_season": await self._async_update_heating(),
                "current_date": _local_now(),
                "address": address,
            }

    async def _async_update_heating(self) -> dict[str, str | None]:
        """
        Refresh heating-season dates from the official RSS feeds.

        RSS problems are non-fatal: the previously stored dates are kept so a
        transient feed outage never hides an already announced season date.
        """
        state = await self._async_load_heating_state()
        xml_text = await async_fetch_rss(async_get_clientsession(self.hass))
        if xml_text is None:
            return state
        merged = merge_heating_state(state, parse_heating_events(xml_text))
        if merged != state:
            self._heating_state = merged
            if self._heating_store is not None:
                await self._heating_store.async_save(merged)
        return self._heating_state

    async def _async_load_heating_state(self) -> dict[str, str | None]:
        """Load the persisted heating-season state once."""
        if self._heating_store is None:
            store: Store[dict[str, str | None]] = Store(
                self.hass,
                1,
                f"{DOMAIN}_heating_{self.config_entry.entry_id}",
            )
            self._heating_store = store
            stored = await store.async_load()
            if isinstance(stored, dict):
                self._heating_state = {
                    "start": stored.get("start"),
                    "end": stored.get("end"),
                }
        return self._heating_state
