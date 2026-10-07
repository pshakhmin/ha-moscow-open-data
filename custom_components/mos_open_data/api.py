"""API Client for Moscow Open Data."""

from __future__ import annotations

import asyncio
import math
import re
import socket
from contextlib import suppress
from http import HTTPStatus
from typing import Any

import aiohttp

from .const import API_BASE_URL, DATASET_HOT_WATER

_TOKEN_SPLIT_RE = re.compile(r"[\s,.]+")

_STOPWORDS = frozenset(
    {
        "москва",
        "город",
        "ул",
        "улица",
        "д",
        "дом",
        "корпус",
        "к",
        "строение",
        "стр",
        "кв",
        "квартира",
        "проспект",
        "пр",
        "переулок",
        "пер",
        "шоссе",
        "бульвар",
        "проезд",
        "набережная",
        "наб",
        "площадь",
        "пл",
        "аллея",
        "тупик",
    }
)


class MosOpenDataApiClientError(Exception):
    """Exception to indicate a general API error."""


class MosOpenDataApiClientCommunicationError(
    MosOpenDataApiClientError,
):
    """Exception to indicate a communication error."""


class MosOpenDataApiClientAuthenticationError(
    MosOpenDataApiClientError,
):
    """Exception to indicate an authentication error."""


class MosOpenDataApiClientRateLimitError(
    MosOpenDataApiClientCommunicationError,
):
    """Exception to indicate the API is rate limiting us."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        """Store the backoff period requested by the API."""
        super().__init__(message)
        self.retry_after = retry_after


def _parse_retry_after(response: aiohttp.ClientResponse) -> int:
    """Return the backoff period (whole seconds) from the Retry-After header."""
    value: float | None = None
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        with suppress(ValueError):
            value = float(retry_after)
    if value is not None and math.isfinite(value) and value >= 0:
        return math.ceil(value)
    return 60


def _verify_response_or_raise(response: aiohttp.ClientResponse) -> None:
    """Verify that the response is valid."""
    if response.status in (401, 403):
        msg = "Invalid credentials"
        raise MosOpenDataApiClientAuthenticationError(
            msg,
        )
    if response.status == HTTPStatus.TOO_MANY_REQUESTS:
        msg = "Rate limited by the API"
        raise MosOpenDataApiClientRateLimitError(
            msg,
            retry_after=_parse_retry_after(response),
        )
    response.raise_for_status()


def build_address_filter(address: str | None) -> str | None:
    """Build an OData filter from an address using token matching."""
    if not address:
        return None

    clauses: list[str] = []
    for token in _TOKEN_SPLIT_RE.split(address):
        if not token or token.casefold() in _STOPWORDS:
            continue
        escaped = token.replace("'", "''")
        # The API's `Address eq` is case-insensitive and behaves as a contains
        # match, while `substringof` is case-sensitive and silently returned no
        # rows for differently-cased input. Use `eq` for every token.
        clauses.append(f"Address eq '{escaped}'")

    if not clauses:
        return None
    return " and ".join(clauses)


def _unwrap_cells(rows: list) -> list[dict]:
    """Return the ``Cells`` payload of each row when present."""
    unwrapped: list[dict] = []
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("Cells"), dict):
            unwrapped.append(row["Cells"])
        else:
            unwrapped.append(row)
    return unwrapped


class MosOpenDataApiClient:
    """Client for Moscow Open Data API (data.mos.ru)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str | None = None,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._api_key = api_key

    async def async_get_hot_water_schedule(
        self,
        address: str | None = None,
    ) -> list[dict]:
        """Fetch hot water shutoff schedule from dataset 1401."""
        return await self._fetch_dataset(DATASET_HOT_WATER, address)

    async def _fetch_dataset(
        self,
        dataset_id: str,
        address: str | None = None,
    ) -> list[dict]:
        """Fetch a dataset with optional address filter."""
        filter_str = build_address_filter(address)
        if address and filter_str is None:
            msg = (
                "Address contains no searchable tokens; refusing to fetch "
                "the entire dataset"
            )
            raise MosOpenDataApiClientError(msg)
        records: list[dict] = []
        skip = 0
        top = 1000

        while True:
            batch = await self._fetch_page(
                dataset_id=dataset_id,
                skip=skip,
                top=top,
                filter_str=filter_str,
            )
            if not batch:
                break
            records.extend(batch)
            if len(batch) < top:
                break
            skip += top

        return records

    async def _fetch_page(
        self,
        dataset_id: str,
        skip: int = 0,
        top: int = 1000,
        filter_str: str | None = None,
    ) -> list[dict]:
        """Fetch a single page of a dataset."""
        url = f"{API_BASE_URL}/datasets/{dataset_id}/rows"
        params: dict[str, Any] = {
            "$skip": skip,
            "$top": top,
        }
        if filter_str:
            params["$filter"] = filter_str
        if self._api_key:
            params["api_key"] = self._api_key

        try:
            async with asyncio.timeout(30):
                response = await self._session.get(url, params=params)
                _verify_response_or_raise(response)
                data = await response.json()

            rows = data if isinstance(data, list) else data.get("Rows", [])
            return _unwrap_cells(rows) if isinstance(rows, list) else []

        except TimeoutError as exception:
            msg = f"Timeout fetching Moscow Open Data - {exception}"
            raise MosOpenDataApiClientCommunicationError(
                msg,
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            msg = f"Error fetching Moscow Open Data - {exception}"
            raise MosOpenDataApiClientCommunicationError(
                msg,
            ) from exception
        except MosOpenDataApiClientError:
            raise
        except Exception as exception:  # pylint: disable=broad-except
            msg = f"Unexpected error fetching Moscow Open Data - {exception}"
            raise MosOpenDataApiClientError(
                msg,
            ) from exception
