"""Unit tests for the Moscow heating-season RSS detection."""

from __future__ import annotations

from datetime import date

from custom_components.mos_open_data.heating import (
    HeatingEvent,
    merge_heating_state,
    parse_heating_events,
)

_ITEMS = (
    "<item><title>«МОЭК» 1 октября приступил к подаче тепла в Москве</title>"
    "<pubDate>Thu, 01 Oct 2026 10:55:31 +0000</pubDate></item>",
    "<item><title>«МОЭК» приступил к отключению отопления в Москве</title>"
    "<pubDate>Tue, 28 Apr 2027 09:00:00 +0000</pubDate></item>",
    "<item><title>«МОЭК» завершил отопительный сезон в Москве</title>"
    "<pubDate>Wed, 29 Apr 2027 09:00:00 +0000</pubDate></item>",
    "<item><title>«МОЭК» завершил финальный этап подготовки тепловых сетей "
    "к отопительному сезону - температурные испытания</title>"
    "<pubDate>Tue, 01 Sep 2026 10:14:58 +0000</pubDate></item>",
    "<item><title>«МОЭК»: 24304 дома получили горячую воду после отключения "
    "для профилактики теплосетей</title>"
    "<pubDate>Tue, 21 Jul 2026 11:48:25 +0000</pubDate></item>",
    "<item><title>«МОЭК» провел перекладку теплосетей для строительства "
    "новой станции метро</title>"
    "<pubDate>Mon, 07 Sep 2026 13:11:53 +0000</pubDate></item>",
)
_HEADER = '<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0"><channel>\n'
RSS = _HEADER + "\n".join(_ITEMS) + "\n</channel></rss>"


def test_parse_classifies_start_and_end() -> None:
    """A supply notice is a start; shutdown notices are ends."""
    events = parse_heating_events(RSS)
    assert [e.date for e in events if e.kind == "start"] == [date(2026, 10, 1)]
    assert [e.date for e in events if e.kind == "end"] == [
        date(2027, 4, 28),
        date(2027, 4, 29),
    ]


def test_parse_ignores_hot_water_prep_and_engineering() -> None:
    """Only the true season boundaries survive (3 of 6 items)."""
    assert len(parse_heating_events(RSS)) == 3


def test_parse_invalid_xml_returns_empty() -> None:
    """Broken XML never raises."""
    assert parse_heating_events("<not-rss") == []


def test_parse_skips_items_without_usable_date() -> None:
    """An item without a parsable pubDate is skipped."""
    xml = (
        "<rss><channel><item>"
        "<title>приступил к подаче тепла</title>"
        "</item></channel></rss>"
    )
    assert parse_heating_events(xml) == []


def test_parse_ignores_ambiguous_start_words() -> None:
    """A phrase meaning "since the beginning" is not a season start."""
    xml = (
        "<rss><channel>"
        "<item><title>«МОЭК» обеспечил подключение 100 школ к системе "
        "теплоснабжения к началу учебного года</title>"
        "<pubDate>Mon, 05 Oct 2026 15:00:58 +0000</pubDate></item>"
        "<item><title>«МОЭК»: количество переходов на электронные квитанции "
        "за тепло увеличилось на 75% с начала года</title>"  # noqa: RUF001
        "<pubDate>Mon, 10 Aug 2026 10:30:37 +0000</pubDate></item>"
        "</channel></rss>"
    )
    assert parse_heating_events(xml) == []


def test_merge_sets_start_then_end() -> None:
    """Start and a later end are both recorded."""
    state = merge_heating_state(
        {"start": None, "end": None}, [HeatingEvent("start", date(2026, 10, 1))]
    )
    assert state == {"start": "2026-10-01", "end": None}
    state = merge_heating_state(state, [HeatingEvent("end", date(2027, 4, 28))])
    assert state == {"start": "2026-10-01", "end": "2027-04-28"}


def test_merge_new_start_clears_old_end() -> None:
    """A newer season start drops the previous season's end."""
    state: dict[str, str | None] = {"start": "2025-10-01", "end": "2026-04-28"}
    merged = merge_heating_state(state, [HeatingEvent("start", date(2026, 9, 24))])
    assert merged == {"start": "2026-09-24", "end": None}


def test_merge_end_without_start_is_ignored() -> None:
    """An end without any known start cannot form a season."""
    merged = merge_heating_state(
        {"start": None, "end": None}, [HeatingEvent("end", date(2027, 4, 28))]
    )
    assert merged == {"start": None, "end": None}


def test_merge_is_idempotent() -> None:
    """Merging the same events again changes nothing."""
    events = [
        HeatingEvent("start", date(2026, 10, 1)),
        HeatingEvent("end", date(2027, 4, 28)),
    ]
    once = merge_heating_state({"start": None, "end": None}, events)
    assert merge_heating_state(once, events) == once
