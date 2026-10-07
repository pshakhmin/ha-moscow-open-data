"""
Unit tests for the pure helpers on the mos_open_data binary sensor.

Only the static/near-static helpers are exercised; no coordinator or network is
involved. The module's ``_local_now`` helper is patched per test so results do
not depend on the wall clock.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

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
# _is_heating_season (date-only logic, so callable without a coordinator)
# ---------------------------------------------------------------------------


def _heating_season_at(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> bool:
    """Evaluate _is_heating_season as if now were ``moment``."""
    monkeypatch.setattr(binary_sensor_module, "_local_now", lambda: moment)
    return binary_sensor_module.MosOpenDataBinarySensor._is_heating_season(object())


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2024, 10, 1, tzinfo=UTC), True),
        (datetime(2024, 12, 15, tzinfo=UTC), True),
        (datetime(2025, 1, 1, tzinfo=UTC), True),
        (datetime(2025, 5, 14, tzinfo=UTC), True),
        (datetime(2025, 5, 15, tzinfo=UTC), True),  # last day of season
        (datetime(2025, 5, 16, tzinfo=UTC), False),
        (datetime(2024, 9, 30, tzinfo=UTC), False),
        (datetime(2024, 6, 15, tzinfo=UTC), False),
    ],
)
def test_is_heating_season(
    monkeypatch: pytest.MonkeyPatch, moment: datetime, expected: bool
) -> None:
    """Heating season runs Oct 1 - May 15 inclusive."""
    assert _heating_season_at(monkeypatch, moment) is expected
