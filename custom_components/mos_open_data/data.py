"""Custom types for mos_open_data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import MosOpenDataApiClient
    from .coordinator import MosOpenDataUpdateCoordinator


type MosOpenDataConfigEntry = ConfigEntry[MosOpenDataData]


@dataclass
class MosOpenDataData:
    """Data for the Moscow Open Data integration."""

    client: MosOpenDataApiClient
    coordinator: MosOpenDataUpdateCoordinator
    integration: Integration
    address: str = ""
