"""Binary sensor platform for mos_open_data."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .entity import MosOpenDataEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MosOpenDataUpdateCoordinator
    from .data import MosOpenDataConfigEntry


def _local_now() -> datetime:
    """Return the current time as a timezone-aware local datetime."""
    return datetime.now(tz=UTC).astimezone()


ENTITY_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="heating_season",
        name="Отопительный сезон активен",
        icon="mdi:radiator",
    ),
    BinarySensorEntityDescription(
        key="water_shutoff",
        name="Горячая вода отключена",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:water-off",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: MosOpenDataConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary_sensor platform."""
    async_add_entities(
        MosOpenDataBinarySensor(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    )


class MosOpenDataBinarySensor(MosOpenDataEntity, BinarySensorEntity):
    """mos_open_data binary_sensor class."""

    def __init__(
        self,
        coordinator: MosOpenDataUpdateCoordinator,
        entity_description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary_sensor class."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.key}"
        )

    @property
    def is_on(self) -> bool:
        """Return true if the binary_sensor is on."""
        key = self.entity_description.key
        data = self.coordinator.data

        if not data:
            return False

        if key == "heating_season":
            return self._is_heating_season()
        if key == "water_shutoff":
            return self._is_water_shutoff(data.get("hot_water_records", []))

        return False

    def _is_heating_season(self) -> bool:
        """
        Check whether the heating season is currently active.

        Based on the dates detected from the official announcements. Without a
        detected start the season state is unknown, so it reports off.
        """
        data = self.coordinator.data or {}
        season = data.get("heating_season") or {}
        start = _parse_iso_date(season.get("start"))
        if start is None:
            return False
        end = _parse_iso_date(season.get("end"))
        today = _local_now().date()
        return today >= start and (end is None or today <= end)

    @staticmethod
    def _is_water_shutoff(records: list[dict]) -> bool:
        """Check if water is currently being shut off."""
        now = _local_now()
        for record in records:
            periods = record.get("Periods") or []
            if isinstance(periods, dict):
                periods = [periods]
            for period in periods:
                if not isinstance(period, dict):
                    continue
                outage_begin = period.get("OutageBegin")
                outage_end = period.get("OutageEnd")
                if outage_begin and outage_end:
                    begin = _parse_datetime(outage_begin)
                    end = _parse_datetime(outage_end)
                    if begin and end and begin <= now <= end:
                        return True
        return False


def _parse_iso_date(value: str | None) -> date | None:
    """Parse an ISO date string, returning None when absent or invalid."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_datetime(value: str | datetime) -> datetime | None:
    """Parse a datetime from string or return as-is."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=_local_now().tzinfo)
        return value
    if isinstance(value, str):
        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).replace(
                    tzinfo=_local_now().tzinfo,
                )
            except ValueError:
                continue
    return None
