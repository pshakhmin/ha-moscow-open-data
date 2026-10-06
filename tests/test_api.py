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
    _build_filter,
    _parse_retry_after,
    _verify_response_or_raise,
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
# _build_filter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("address", [None, ""])
def test_build_filter_empty_address_returns_none(address: str | None) -> None:
    """No address means no OData filter."""
    assert _build_filter(address) is None


def test_build_filter_produces_odata_equality() -> None:
    """A normal address becomes an OData equality filter."""
    assert _build_filter("ул. Тверская, 1") == "Address eq 'ул. Тверская, 1'"


def test_build_filter_escapes_single_quotes() -> None:
    """OData escapes single quotes by doubling them."""
    assert _build_filter("O'Brien St.") == "Address eq 'O''Brien St.'"


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
