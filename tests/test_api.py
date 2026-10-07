"""
Unit tests for the Moscow Open Data API helpers.

These are pure unit tests: ``api.py`` only imports ``aiohttp`` and ``const``,
so no Home Assistant harness or network access is required. All responses are
lightweight fakes.
"""

from __future__ import annotations

from unittest.mock import Mock

import aiohttp
import pytest

from custom_components.mos_open_data.api import (
    MosOpenDataApiClientAuthenticationError,
    MosOpenDataApiClientRateLimitError,
    _parse_retry_after,
    _unwrap_cells,
    _verify_response_or_raise,
    build_address_filter,
)


class _FakeResponse:
    """Minimal stand-in for :class:`aiohttp.ClientResponse`."""

    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        """Mimic aiohttp raising for non-success statuses."""
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=Mock(),
                history=(),
                status=self.status,
            )


# ---------------------------------------------------------------------------
# build_address_filter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("address", [None, "", "   "])
def test_build_filter_empty_address_returns_none(address: str | None) -> None:
    """No address means no OData filter."""
    assert build_address_filter(address) is None


def test_build_filter_only_stopwords_returns_none() -> None:
    """An address made only of generic words yields no filter."""
    assert build_address_filter("Москва, улица, дом") is None


def test_build_filter_token_strategy() -> None:
    """Every token becomes a case-insensitive ``Address eq`` clause."""
    assert build_address_filter("ул. Тверская, д. 10") == (
        "Address eq 'Тверская' and Address eq '10'"
    )


def test_build_filter_multiple_tokens() -> None:
    """Generic words are dropped while street and house are kept."""
    assert build_address_filter("Москва, улица Ленина, дом 1") == (
        "Address eq 'Ленина' and Address eq '1'"
    )


def test_build_filter_preserves_house_fractions() -> None:
    """House numbers with a slash stay intact as a single token."""
    assert build_address_filter("Тверская 10/1") == (
        "Address eq 'Тверская' and Address eq '10/1'"
    )


def test_build_filter_escapes_single_quotes() -> None:
    """OData escapes single quotes by doubling them."""
    assert build_address_filter("ул. O'Brien, д. 10") == (
        "Address eq 'O''Brien' and Address eq '10'"
    )


def test_build_filter_is_not_case_sensitive() -> None:
    """Lower-case input is kept verbatim; the API matches it case-insensitively."""
    assert build_address_filter("тверская улица, дом 10") == (
        "Address eq 'тверская' and Address eq '10'"
    )


def test_build_filter_never_uses_substringof() -> None:
    """The case-sensitive ``substringof`` operator must not be emitted."""
    result = build_address_filter("Тверская улица, дом 19")
    assert result is not None
    assert "substringof" not in result


# ---------------------------------------------------------------------------
# _unwrap_cells
# ---------------------------------------------------------------------------


def test_unwrap_cells_returns_cells_payload() -> None:
    """A Cells-wrapped row is replaced by its Cells payload."""
    rows = [{"global_id": 1, "Cells": {"Address": "ул. Тверская, 10"}}]
    assert _unwrap_cells(rows) == [{"Address": "ул. Тверская, 10"}]


def test_unwrap_cells_leaves_plain_dict_unchanged() -> None:
    """A row without a Cells dict is returned as-is."""
    row = {"Address": "ул. Тверская, 10"}
    assert _unwrap_cells([row]) == [row]


def test_unwrap_cells_non_dict_cells() -> None:
    """A non-dict Cells value leaves the row unchanged."""
    row = {"Cells": "not-a-dict"}
    assert _unwrap_cells([row]) == [row]


def test_unwrap_cells_non_dict_row() -> None:
    """Non-dict rows are passed through unchanged."""
    assert _unwrap_cells(["not-a-row"]) == ["not-a-row"]


# ---------------------------------------------------------------------------
# _parse_retry_after
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("5", 5),
        ("5.2", 6),  # rounded up to whole seconds
        ("0", 0),
        (None, 60),  # header missing -> default
        ("abc", 60),  # not numeric -> default
        ("-1", 60),  # negative -> default
        ("inf", 60),  # non-finite -> default
        ("nan", 60),  # non-finite -> default
    ],
)
def test_parse_retry_after(header: str | None, expected: int) -> None:
    """Parse the Retry-After header, defaulting to 60 seconds."""
    headers = {} if header is None else {"Retry-After": header}
    assert _parse_retry_after(_FakeResponse(429, headers)) == expected


# ---------------------------------------------------------------------------
# _verify_response_or_raise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_verify_raises_authentication_error(status: int) -> None:
    """401/403 are reported as authentication errors."""
    with pytest.raises(MosOpenDataApiClientAuthenticationError):
        _verify_response_or_raise(_FakeResponse(status))


def test_verify_raises_rate_limit_error_with_header() -> None:
    """429 is reported as a rate-limit error carrying the requested backoff."""
    with pytest.raises(MosOpenDataApiClientRateLimitError) as exc_info:
        _verify_response_or_raise(_FakeResponse(429, {"Retry-After": "30"}))
    assert exc_info.value.retry_after == 30


def test_verify_raises_rate_limit_error_without_header() -> None:
    """429 without a usable header falls back to the 60s default."""
    with pytest.raises(MosOpenDataApiClientRateLimitError) as exc_info:
        _verify_response_or_raise(_FakeResponse(429))
    assert exc_info.value.retry_after == 60


def test_verify_accepts_success() -> None:
    """A success status does not raise."""
    _verify_response_or_raise(_FakeResponse(200))


def test_verify_propagates_other_http_errors() -> None:
    """Non-handled error statuses go through raise_for_status()."""
    with pytest.raises(aiohttp.ClientResponseError):
        _verify_response_or_raise(_FakeResponse(500))
