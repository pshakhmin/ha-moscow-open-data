"""
Unit tests for the pure helpers on the mos_open_data binary sensor.

Only the static/near-static helpers are exercised; no coordinator or network is
involved. The module's ``_local_now`` helper is patched per test so results do
not depend on the wall clock.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.mos_open_data import binary_sensor as binary_sensor_module

FIXED_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _freeze_now(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the module's idea of "now"."""
    monkeypatch.setattr(binary_sensor_module, "_local_now", lambda: FIXED_NOW)


# ---------------------------------------------------------------------------
# _is_water_shutoff
# ---------------------------------------------------------------------------


def test_water_shutoff_periods_as_list() -> None:
    """A period covering now is detected when Periods is a list."""
    records = [
        {
            "Periods": [
                {
                    "OutageBegin": "14.06.2024 00:00:00",
                    "OutageEnd": "16.06.2024 23:59:59",
                }
            ]
        }
    ]
    assert (
        binary_sensor_module.MosOpenDataBinarySensor._is_water_shutoff(records) is True
    )


def test_water_shutoff_periods_as_dict() -> None:
    """A single period object (dict form) is handled as well."""
    records = [{"Periods": {"OutageBegin": "14.06.2024", "OutageEnd": "16.06.2024"}}]
    assert (
        binary_sensor_module.MosOpenDataBinarySensor._is_water_shutoff(records) is True
    )


def test_water_shutoff_outside_window_is_false() -> None:
    """A period entirely in the past does not count."""
    records = [{"Periods": [{"OutageBegin": "01.06.2024", "OutageEnd": "02.06.2024"}]}]
    assert (
        binary_sensor_module.MosOpenDataBinarySensor._is_water_shutoff(records) is False
    )


def test_water_shutoff_missing_periods_is_false() -> None:
    """Records without usable periods are ignored."""
    records: list[dict] = [{}, {"Periods": None}, {"Periods": []}]
    assert (
        binary_sensor_module.MosOpenDataBinarySensor._is_water_shutoff(records) is False
    )


def test_water_shutoff_unparseable_dates_is_false() -> None:
    """Unparseable dates do not crash and do not count as an outage."""
    records = [{"Periods": [{"OutageBegin": "not-a-date", "OutageEnd": "also-bad"}]}]
    assert (
        binary_sensor_module.MosOpenDataBinarySensor._is_water_shutoff(records) is False
    )


# ---------------------------------------------------------------------------
# _is_heating_season (reads the detected season dates from coordinator data)
# ---------------------------------------------------------------------------


def _heating_season_at(
    monkeypatch: pytest.MonkeyPatch, data: dict, moment: datetime
) -> bool:
    """Evaluate _is_heating_season for a payload as if now were ``moment``."""
    monkeypatch.setattr(binary_sensor_module, "_local_now", lambda: moment)
    stub = SimpleNamespace(coordinator=SimpleNamespace(data=data))
    return binary_sensor_module.MosOpenDataBinarySensor._is_heating_season(stub)


SEASON = {"heating_season": {"start": "2026-10-01", "end": "2027-05-15"}}


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2026, 10, 1, tzinfo=UTC), True),  # first day
        (datetime(2026, 12, 15, tzinfo=UTC), True),
        (datetime(2027, 1, 1, tzinfo=UTC), True),
        (datetime(2027, 5, 15, tzinfo=UTC), True),  # last day
        (datetime(2027, 5, 16, tzinfo=UTC), False),
        (datetime(2026, 9, 30, tzinfo=UTC), False),
    ],
)
def test_is_heating_season(
    monkeypatch: pytest.MonkeyPatch, moment: datetime, expected: bool
) -> None:
    """The season is active between the detected start and end dates."""
    assert _heating_season_at(monkeypatch, SEASON, moment) is expected


def test_is_heating_season_pending_end_stays_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An announced start without an end means the season is still on."""
    data = {"heating_season": {"start": "2026-10-01", "end": None}}
    assert _heating_season_at(monkeypatch, data, datetime(2026, 12, 1, tzinfo=UTC))
    assert not _heating_season_at(monkeypatch, data, datetime(2026, 9, 30, tzinfo=UTC))


def test_is_heating_season_unknown_start_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a detected start the state is unknown, reported as off."""
    data = {"heating_season": {"start": None, "end": None}}
    assert not _heating_season_at(monkeypatch, data, datetime(2027, 1, 1, tzinfo=UTC))


def test_is_heating_season_missing_data_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing coordinator data is handled without crashing."""
    assert not _heating_season_at(monkeypatch, {}, FIXED_NOW)


def test_binary_sensor_device_classes() -> None:
    """Device classes give clear labels instead of misleading ones."""
    by_key = {d.key: d for d in binary_sensor_module.ENTITY_DESCRIPTIONS}
    assert by_key["water_shutoff"].device_class is BinarySensorDeviceClass.PROBLEM
    assert by_key["heating_season"].device_class is None
