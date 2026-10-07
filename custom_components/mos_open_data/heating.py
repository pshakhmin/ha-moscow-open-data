"""Detect real Moscow heating-season dates from official RSS announcements."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Literal
from xml.etree import ElementTree as ET

import aiohttp

from .const import LOGGER

# МОЭК is the primary publisher; mos.ru is a fallback.
RSS_FEEDS: tuple[str, ...] = (
    "https://www.moek.ru/rss/",
    "https://www.mos.ru/rss/",
)

# Items that mention heat but are not a season boundary: hot-water (ГВС)
# notices, preparation/maintenance and hydraulic tests.
_IGNORE_RE = re.compile(
    r"горяч|гвс|профилакт|подготов|готовност|испытан",
    re.IGNORECASE,
)
# "отоп" covers both "отопление" and "отопительный", which "тепл" misses.
_HEAT_RE = re.compile(r"тепл|отоп", re.IGNORECASE)
# Shutdown is checked before supply, so "приступил к отключению" is an end.
_END_RE = re.compile(r"отключ|заверш|прекрат|выключ", re.IGNORECASE)
# "начал" is intentionally absent: it also matches "с начала".  # noqa: RUF003
_START_RE = re.compile(r"подач|подава|включ|возобнов|приступ", re.IGNORECASE)


@dataclass(frozen=True)
class HeatingEvent:
    """A heating-season start or end announced in a news item."""

    kind: Literal["start", "end"]
    date: date


def _classify(title: str) -> Literal["start", "end"] | None:
    """Classify a news title as a season start/end, or None when irrelevant."""
    if _IGNORE_RE.search(title) or not _HEAT_RE.search(title):
        return None
    if _END_RE.search(title):
        return "end"
    if _START_RE.search(title):
        return "start"
    return None


def _item_date(pub_date: str | None) -> date | None:
    """Parse an RSS pubDate into a local date."""
    if not pub_date:
        return None
    try:
        parsed = parsedate_to_datetime(pub_date)
    except TypeError, ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.date()


def parse_heating_events(xml_text: str) -> list[HeatingEvent]:
    """Extract heating-season start/end events from an RSS document."""
    try:
        root = ET.fromstring(xml_text)  # noqa: S314 (trusted official feed)
    except ET.ParseError:
        return []

    events: list[HeatingEvent] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        kind = _classify(title) if title else None
        if kind is None:
            continue
        published = _item_date(item.findtext("pubDate"))
        if published is None:
            continue
        events.append(HeatingEvent(kind=kind, date=published))
    return events


def _parse_iso(value: str | None) -> date | None:
    """Parse an ISO date string, returning None when absent or invalid."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def merge_heating_state(
    state: dict[str, str | None],
    events: list[HeatingEvent],
) -> dict[str, str | None]:
    """Merge detected events into the persisted state without mutating it."""
    start = _parse_iso(state.get("start"))
    end = _parse_iso(state.get("end"))

    starts = [event.date for event in events if event.kind == "start"]
    if starts:
        newest_start = max(starts)
        if start is None or newest_start > start:
            start = newest_start
            if end is not None and end <= start:
                end = None

    ends = [event.date for event in events if event.kind == "end"]
    if ends:
        newest_end = max(ends)
        if (
            start is not None
            and newest_end > start
            and (end is None or newest_end > end)
        ):
            end = newest_end

    return {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
    }


async def async_fetch_rss(session: aiohttp.ClientSession) -> str | None:
    """Fetch the first RSS feed that returns parseable XML, or None."""
    for url in RSS_FEEDS:
        try:
            async with asyncio.timeout(20):
                async with session.get(url) as response:
                    response.raise_for_status()
                    text = await response.text()
        except (TimeoutError, aiohttp.ClientError) as exception:
            LOGGER.warning("Could not fetch heating RSS %s: %s", url, exception)
            continue
        try:
            ET.fromstring(text)  # noqa: S314 (trusted official feed)
        except ET.ParseError as exception:
            LOGGER.warning("Invalid heating RSS %s: %s", url, exception)
            continue
        return text
    return None
