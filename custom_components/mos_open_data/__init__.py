"""Custom integration to integrate mos_open_data with Home Assistant.

For more details about this integration, please refer to
https://developers.home-assistant.io/docs/creating_integration_index
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

from .api import MosOpenDataApiClient
from .const import (
    ATTRIBUTION,
    CONF_ADDRESS,
    CONF_API_KEY,
    DOMAIN,
    LOGGER,
    UPDATE_INTERVAL_SECONDS,
)
from .coordinator import MosOpenDataUpdateCoordinator
from .data import MosOpenDataData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import MosOpenDataConfigEntry

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(
    hass: HomeAssistant,
    entry: MosOpenDataConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    api_key = entry.data.get(CONF_API_KEY) or None
    coordinator = MosOpenDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        config_entry=entry,
    )
    entry.runtime_data = MosOpenDataData(
        client=MosOpenDataApiClient(
            session=async_get_clientsession(hass),
            api_key=api_key,
        ),
        integration=async_get_loaded_integration(hass, entry.domain),
        coordinator=coordinator,
        address=entry.data.get(CONF_ADDRESS, ""),
    )

    # https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: MosOpenDataConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
