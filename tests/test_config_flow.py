"""
Config-flow tests for the mos_open_data integration.

These use the Home Assistant test harness (``pytest-homeassistant-custom-component``)
and mock the API client so nothing touches data.mos.ru.
"""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType

from custom_components.mos_open_data.api import (
    MosOpenDataApiClient,
    MosOpenDataApiClientAuthenticationError,
    MosOpenDataApiClientCommunicationError,
)
from custom_components.mos_open_data.const import CONF_API_KEY, DOMAIN

VALID_API_KEY = "test-api-key"


async def test_user_form_is_shown(hass, enable_custom_integrations) -> None:
    """Starting the flow from the user source shows the address form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_successful_connection_creates_entry(
    hass, enable_custom_integrations, monkeypatch
) -> None:
    """A successful (mocked) API check creates the config entry."""

    async def _fake_get_schedule(self, address=None):  # noqa: ANN202
        return []

    monkeypatch.setattr(
        MosOpenDataApiClient, "async_get_hot_water_schedule", _fake_get_schedule
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ADDRESS: "ул. Тверская, 1", CONF_API_KEY: VALID_API_KEY},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "ул. Тверская, 1"
    assert result["data"] == {
        CONF_ADDRESS: "ул. Тверская, 1",
        CONF_API_KEY: VALID_API_KEY,
    }


async def test_missing_api_key_reshows_form(hass, enable_custom_integrations) -> None:
    """A blank API key is rejected before any API call is made."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ADDRESS: "ул. Тверская, 1", CONF_API_KEY: "   "},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "missing_api_key"


async def test_invalid_address_reshows_form(hass, enable_custom_integrations) -> None:
    """An address with no searchable tokens is rejected before any API call."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ADDRESS: "Москва, дом", CONF_API_KEY: "k"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_address"


async def test_invalid_auth_reshows_form(
    hass, enable_custom_integrations, monkeypatch
) -> None:
    """An authentication error is surfaced as invalid_auth."""

    async def _failing_get_schedule(self, address=None):  # noqa: ANN202
        raise MosOpenDataApiClientAuthenticationError("nope")

    monkeypatch.setattr(
        MosOpenDataApiClient, "async_get_hot_water_schedule", _failing_get_schedule
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ADDRESS: "ул. Тверская, 1", CONF_API_KEY: VALID_API_KEY},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_connection_error_reshows_form(
    hass, enable_custom_integrations, monkeypatch
) -> None:
    """A communication error is surfaced as a form error, not a crash."""

    async def _failing_get_schedule(self, address=None):  # noqa: ANN202
        raise MosOpenDataApiClientCommunicationError("boom")

    monkeypatch.setattr(
        MosOpenDataApiClient, "async_get_hot_water_schedule", _failing_get_schedule
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ADDRESS: "ул. Тверская, 1", CONF_API_KEY: VALID_API_KEY},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "connection"
