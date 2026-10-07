"""
Unit tests for the date-selection logic on the mos_open_data sensor.

The selection helpers are pure date math. ``current_date`` is injected through a
tiny coordinator stub, and the module's ``_local_now`` helper is patched where a
fixed "now" is needed, so every case is deterministic.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from custom_components.mos_open_data import sensor as sensor_module
from custom_components.mos_open_data.sensor import MosOpenDataSensor

# ---------------------------------------------------------------------------
# _extract_shutoff_dates
# ---------------------------------------------------------------------------


def _extract(records: list[dict], field: str) -> list[datetime]:
    return MosOpenDataSensor._extract_shutoff_dates(records, field)


def _extracted_date(records: list[dict], field: str) -> list[date]:
    """Extract only the date parts (timezone handling is not under test here)."""
    return [value.date() for value in _extract(records, field)]


def test_extract_list_form_supports_multiple_formats() -> None:
    """Periods-as-list and all supported date formats are parsed."""
    records = [
        {
            "Periods": [
                {"OutageBegin": "10.06.2024", "OutageEnd": "20.06.2024 18:30:00"},
                {"OutageBegin": "2024-07-01", "OutageEnd": "2024-07-05T09:00:00"},
            ]
        }
    ]
    assert _extracted_date(records, "OutageBegin") == [
        date(2024, 6, 10),
        date(2024, 7, 1),
    ]


def test_extract_dict_form_is_supported() -> None:
    """A single Periods dict is treated like a one-element list."""
    records = [{"Periods": {"OutageBegin": "10.06.2024", "OutageEnd": "20.06.2024"}}]
    assert _extracted_date(records, "OutageBegin") == [date(2024, 6, 10)]


def test_extract_ignores_missing_and_unparseable_values() -> None:
    """Missing fields, junk values and junk periods are skipped safely."""
    records = [
        {"Periods": [{"OutageEnd": "20.06.2024"}, {"OutageBegin": "bogus"}, "junk"]},
        {},
    ]
    assert _extract(records, "OutageBegin") == []


# ---------------------------------------------------------------------------
# next shutoff start / end selection
# ---------------------------------------------------------------------------


def _stub(records: list[dict], current_date: datetime) -> SimpleNamespace:
    """Build a minimal stand-in ``self`` for the instance helpers."""
    stub = SimpleNamespace(
        coordinator=SimpleNamespace(data={"current_date": current_date})
    )
    stub._extract_shutoff_dates = MosOpenDataSensor._extract_shutoff_dates
    return stub


def _next(records: list[dict], current_date: datetime, method_name: str) -> str | None:
    return getattr(MosOpenDataSensor, method_name)(
        _stub(records, current_date), records
    )


def test_next_start_returns_earliest_future_date() -> None:
    """The earliest begin date on/after today is returned."""
    records = [
        {
            "Periods": [
                {"OutageBegin": "10.06.2024"},
                {"OutageBegin": "01.08.2024"},
                {"OutageBegin": "20.06.2024"},
            ]
        }
    ]
    assert _next(records, datetime(2024, 6, 15), "_get_next_shutoff_start") == (
        "20.06.2024"
    )


def test_next_start_includes_today() -> None:
    """A date equal to today counts as upcoming."""
    records = [{"Periods": [{"OutageBegin": "15.06.2024"}]}]
    assert _next(records, datetime(2024, 6, 15, 23, 0), "_get_next_shutoff_start") == (
        "15.06.2024"
    )


def test_next_start_falls_back_to_last_extracted_when_all_past() -> None:
    """With only past dates, the last extracted one is returned."""
    records = [
        {"Periods": [{"OutageBegin": "10.06.2024"}, {"OutageBegin": "20.06.2024"}]}
    ]
    assert _next(records, datetime(2024, 7, 1), "_get_next_shutoff_start") == (
        "20.06.2024"
    )


def test_next_start_none_when_empty() -> None:
    """No records means no date."""
    assert _next([], datetime(2024, 6, 15), "_get_next_shutoff_start") is None


def test_next_end_returns_earliest_future_date() -> None:
    """The earliest end date on/after today is returned."""
    records = [
        {
            "Periods": [
                {"OutageEnd": "20.06.2024"},
                {"OutageEnd": "25.06.2024"},
                {"OutageEnd": "18.06.2024"},
            ]
        }
    ]
    assert (
        _next(records, datetime(2024, 6, 15), "_get_next_shutoff_end") == "18.06.2024"
    )


# ---------------------------------------------------------------------------
# heating season start / end
# ---------------------------------------------------------------------------


def _heating_value(
    monkeypatch: pytest.MonkeyPatch, moment: datetime, method_name: str
) -> str | None:
    """Evaluate a heating-season helper as if now were ``moment``."""
    monkeypatch.setattr(sensor_module, "_local_now", lambda: moment)
    method = getattr(MosOpenDataSensor, method_name)
    return method(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2024, 6, 15, tzinfo=UTC), "01.10.2024"),  # off-season -> next
        (datetime(2024, 10, 1, tzinfo=UTC), "01.10.2024"),  # in season
        (datetime(2024, 12, 31, tzinfo=UTC), "01.10.2024"),  # in season
        (datetime(2025, 3, 1, tzinfo=UTC), "01.10.2024"),  # in season
        (datetime(2026, 10, 8, tzinfo=UTC), "01.10.2026"),  # reported case
    ],
)
def test_heating_season_start(
    monkeypatch: pytest.MonkeyPatch, moment: datetime, expected: str
) -> None:
    """Start is the Oct 1 of the current or next heating season."""
    assert _heating_value(monkeypatch, moment, "_get_heating_season_start") == expected


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2024, 6, 15, tzinfo=UTC), "15.05.2025"),  # off-season -> next
        (datetime(2024, 5, 15, tzinfo=UTC), "15.05.2024"),  # last day of season
        (datetime(2025, 3, 1, tzinfo=UTC), "15.05.2025"),  # in season
        (datetime(2025, 6, 1, tzinfo=UTC), "15.05.2026"),  # off-season -> next
        (datetime(2026, 10, 8, tzinfo=UTC), "15.05.2027"),  # reported case
    ],
)
def test_heating_season_end(
    monkeypatch: pytest.MonkeyPatch, moment: datetime, expected: str
) -> None:
    """End is the May 15 of the current or next heating season (after start)."""
    assert _heating_value(monkeypatch, moment, "_get_heating_season_end") == expected


def test_heating_season_start_is_before_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start and end describe the same season, so start is always before end."""
    moment = datetime(2026, 10, 8, tzinfo=UTC)
    start = _heating_value(monkeypatch, moment, "_get_heating_season_start")
    end = _heating_value(monkeypatch, moment, "_get_heating_season_end")
    assert start == "01.10.2026"
    assert end == "15.05.2027"
