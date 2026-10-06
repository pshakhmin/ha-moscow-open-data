"""Binary sensor platform for mos_open_data."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .const import (
    HEATING_SEASON_END_DAY,
    HEATING_SEASON_END_MONTH,
)
from .entity import MosOpenDataEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MosOpenDataUpdateCoordinator
    from .data import MosOpenDataConfigEntry


ENTITY_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="heating_season",
        name="Отопительный сезон активен",
        device_class=BinarySensorDeviceClass.HEAT,
        icon="mdi:radiator",
    ),
    BinarySensorEntityDescription(
        key="water_shutoff",
        name="Горячая вода отключена",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:water-off",
    ),
    BinarySensorEntityDescription(
        key="air_quality_alert",
        name="Превышение ПДК загрязнения воздуха",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:alert-circle",
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
        if key == "air_quality_alert":
            return self._has_air_quality_exceedance(data.get("air_quality_records", []))

        return False

    def _is_heating_season(self) -> bool:
        """Check if it's currently the heating season."""
        now = datetime.now()
        month = now.month
        day = now.day

        # Heating season: Oct 1 - May 15 (spans year boundary)
        if month in (10, 11, 12):
            return True
        if month in (1, 2, 3, 4):
            return True
        if month == 5 and day <= HEATING_SEASON_END_DAY:
            return True
        return False

    @staticmethod
    def _is_water_shutoff(records: list[dict]) -> bool:
        """Check if water is currently being shut off."""
        now = datetime.now()
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

    @staticmethod
    def _has_air_quality_exceedance(records: list[dict]) -> bool:
        """Check if any air quality parameter exceeds PDKss safe level."""
        for record in records:
            cells = record.get("Cells") if isinstance(record, dict) else None
            if not cells:
                continue
            pdk_mr = cells.get("PDKmr_ASIL")
            pdk_ss = cells.get("PDKss")
            if pdk_mr is not None and isinstance(pdk_mr, (int, float)) and pdk_mr > 0:
                return True
        return False


def _parse_datetime(value: str | datetime) -> datetime | None:
    """Parse a datetime from string or return as-is."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None
