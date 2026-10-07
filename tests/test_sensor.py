"""
Unit tests for the mos_open_data sensor helpers.

The shutoff-date helpers are pure date math with an injected ``current_date``.
The heating-season helpers read dates detected from the official RSS feed via
the coordinator payload, so a small coordinator stub is used.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

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
# heating season start / end (from detected RSS dates in the coordinator data)
# ---------------------------------------------------------------------------


def _season_value(data: dict, field: str) -> str | None:
    """Evaluate a heating-season helper against a fake coordinator payload."""
    stub = SimpleNamespace(coordinator=SimpleNamespace(data=data))
    return MosOpenDataSensor._get_heating_season(stub, field)


def test_heating_season_dates_from_detected_data() -> None:
    """Detected dates are formatted for display."""
    data = {"heating_season": {"start": "2026-10-01", "end": "2027-05-15"}}
    assert _season_value(data, "start") == "01.10.2026"
    assert _season_value(data, "end") == "15.05.2027"


def test_heating_season_unknown_when_not_announced() -> None:
    """No detection yields None (Unknown) instead of a hardcoded date."""
    data = {"heating_season": {"start": None, "end": None}}
    assert _season_value(data, "start") is None
    assert _season_value(data, "end") is None


def test_heating_season_unknown_without_data() -> None:
    """Absent hearing-season data yields None."""
    assert _season_value({}, "start") is None
    assert _season_value({}, "end") is None


def test_heating_season_end_may_be_pending() -> None:
    """A start announced without an end yet still shows the start."""
    data = {"heating_season": {"start": "2026-10-01", "end": None}}
    assert _season_value(data, "start") == "01.10.2026"
    assert _season_value(data, "end") is None
