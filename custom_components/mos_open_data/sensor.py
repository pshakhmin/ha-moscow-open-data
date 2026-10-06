"""Sensor platform for mos_open_data."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from .const import (
    HEATING_SEASON_END_DAY,
    HEATING_SEASON_END_MONTH,
    HEATING_SEASON_START_DAY,
    HEATING_SEASON_START_MONTH,
)
from .entity import MosOpenDataEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MosOpenDataUpdateCoordinator
    from .data import MosOpenDataConfigEntry


ENTITY_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="next_water_shutoff_date",
        name="Следующее отключение горячей воды",
        icon="mdi:water-off",
    ),
    SensorEntityDescription(
        key="next_water_shutoff_end",
        name="Восстановление горячей воды",
        icon="mdi:water-on",
    ),
    SensorEntityDescription(
        key="heating_season_start",
        name="Начало отопительного сезона",
        icon="mdi:radiator",
    ),
    SensorEntityDescription(
        key="heating_season_end",
        name="Окончание отопительного сезона",
        icon="mdi:radiator-off",
    ),
    SensorEntityDescription(
        key="air_quality_parameters_count",
        name="Контролируемых параметров качества воздуха",
        icon="mdi:air-filter",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: MosOpenDataConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    async_add_entities(
        MosOpenDataSensor(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    )


class MosOpenDataSensor(MosOpenDataEntity, SensorEntity):
    """mos_open_data Sensor class."""

    def __init__(
        self,
        coordinator: MosOpenDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.key}"
        )

    @property
    def native_value(self) -> str | None:
        """Return the native value of the sensor."""
        data = self.coordinator.data
        if not data:
            return None

        key = self.entity_description.key

        if key == "next_water_shutoff_date":
            records = data.get("hot_water_records", [])
            return self._get_next_shutoff_start(records)
        if key == "next_water_shutoff_end":
            records = data.get("hot_water_records", [])
            return self._get_next_shutoff_end(records)
        if key == "heating_season_start":
            return self._get_heating_season_start()
        if key == "heating_season_end":
            return self._get_heating_season_end()
        if key == "air_quality_parameters_count":
            records = data.get("air_quality_records", [])
            return str(len(records))

        return None

    def _get_next_shutoff_start(self, records: list[dict]) -> str | None:
        """Get the start date of the next water shutoff period."""
        now = self.coordinator.data.get("current_date") or datetime.now()
        dates = self._extract_shutoff_dates(records, field="OutageBegin")
        future_dates = sorted(
            (d for d in dates if d.date() >= now.date()),
            key=lambda d: d,
        )
        if future_dates:
            return future_dates[0].strftime("%d.%m.%Y")
        if dates:
            return dates[-1].strftime("%d.%m.%Y")
        return None

    def _get_next_shutoff_end(self, records: list[dict]) -> str | None:
        """Get the end date of the next water shutoff period."""
        now = self.coordinator.data.get("current_date") or datetime.now()
        dates = self._extract_shutoff_dates(records, field="OutageEnd")
        future_dates = sorted(
            (d for d in dates if d.date() >= now.date()),
            key=lambda d: d,
        )
        if future_dates:
            return future_dates[0].strftime("%d.%m.%Y")
        if dates:
            return dates[-1].strftime("%d.%m.%Y")
        return None

    def _get_heating_season_start(self) -> str | None:
        """Return heating season start date."""
        now = datetime.now()
        start = datetime(now.year, HEATING_SEASON_START_MONTH, HEATING_SEASON_START_DAY)
        if start <= now:
            start = datetime(now.year + 1, HEATING_SEASON_START_MONTH, HEATING_SEASON_START_DAY)
        return start.strftime("%d.%m.%Y")

    def _get_heating_season_end(self) -> str | None:
        """Return heating season end date."""
        now = datetime.now()
        end = datetime(now.year, HEATING_SEASON_END_MONTH, HEATING_SEASON_END_DAY)
        if end <= now:
            end = datetime(now.year + 1, HEATING_SEASON_END_MONTH, HEATING_SEASON_END_DAY)
        return end.strftime("%d.%m.%Y")

    @staticmethod
    def _extract_shutoff_dates(
        records: list[dict],
        field: str,
    ) -> list[datetime]:
        """Extract datetime objects from records for a given date field."""
        dates: list[datetime] = []
        for record in records:
            periods = record.get("Periods") or []
            if isinstance(periods, dict):
                periods = [periods]
            for period in periods:
                value = period.get(field) if isinstance(period, dict) else None
                if value:
                    if isinstance(value, datetime):
                        dates.append(value)
                    elif isinstance(value, str):
                        for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                            try:
                                dates.append(datetime.strptime(value, fmt))
                                break
                            except ValueError:
                                continue
        return dates
