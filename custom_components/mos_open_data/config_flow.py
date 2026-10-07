"""Adds config flow for mos_open_data."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration
from slugify import slugify

from .api import (
    MosOpenDataApiClient,
    MosOpenDataApiClientAuthenticationError,
    MosOpenDataApiClientCommunicationError,
    MosOpenDataApiClientError,
    build_address_filter,
)
from .const import CONF_ADDRESS, CONF_API_KEY, DOMAIN, LOGGER


class MosOpenDataFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Moscow Open Data integration."""

    VERSION = 1
    MINOR_VERSION = 0

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        _errors = {}
        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "")
            address = user_input[CONF_ADDRESS]
            if not api_key or not api_key.strip():
                _errors["base"] = "missing_api_key"
            elif build_address_filter(address) is None:
                _errors["base"] = "invalid_address"
            else:
                try:
                    await self._test_connection(
                        address=address,
                        api_key=api_key,
                    )
                except MosOpenDataApiClientAuthenticationError as exception:
                    LOGGER.warning(exception)
                    _errors["base"] = "invalid_auth"
                except MosOpenDataApiClientCommunicationError as exception:
                    LOGGER.warning(exception)
                    _errors["base"] = "connection"
                except MosOpenDataApiClientError as exception:
                    LOGGER.exception(exception)
                    _errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(
                        unique_id=slugify(address),
                    )
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=address,
                        data=user_input,
                    )

        integration = async_get_loaded_integration(self.hass, DOMAIN)
        assert integration.documentation is not None, (  # noqa: S101
            "Integration documentation URL is not set in manifest.json"
        )

        return self.async_show_form(
            step_id="user",
            description_placeholders={
                "documentation_url": integration.documentation,
            },
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ADDRESS,
                        default=(user_input or {}).get(CONF_ADDRESS, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        ),
                    ),
                    vol.Required(
                        CONF_API_KEY,
                        default=(user_input or {}).get(CONF_API_KEY, vol.UNDEFINED),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                },
            ),
            errors=_errors,
        )

    async def _test_connection(
        self,
        address: str,
        api_key: str,
    ) -> None:
        """Validate that we can reach the API."""
        session = async_get_clientsession(self.hass)
        client = MosOpenDataApiClient(session=session, api_key=api_key)
        await client.async_get_hot_water_schedule(address=address)
