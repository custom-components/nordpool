"""Adds config flow for nordpool."""
from collections import OrderedDict

import voluptuous as vol
from homeassistant import config_entries

from . import DOMAIN, _LOGGER
from .sensor import PLATFORM_SCHEMA


@config_entries.HANDLERS.register(DOMAIN)
class BlueprintFlowHandler(config_entries.ConfigFlow):
    """Config flow for Blueprint."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        _LOGGER.info("lo from BlueprintFlowHandler")
        """Initialize."""
        self._errors = {}

    async def async_step_user(
        self, user_input=None
    ):  # pylint: disable=dangerous-default-value
        """Handle a flow initialized by the user."""
        _LOGGER.info("lo from async_step_user")
        self._errors = {}
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if self.hass.data.get(DOMAIN):
            return self.async_abort(reason="single_instance_allowed")

        _LOGGER.info('ass %s' % user_input)
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return await self._show_config_form(user_input)

    async def _show_config_form(self, user_input):
        """Show the configuration form to edit location data."""
        _LOGGER.info("lo from _show_config_form %r", user_input)

        data_schema = OrderedDict()
        data_schema[vol.Required("region", default="Kr.sand")] = str
        data_schema[vol.Optional("name", default="Elspot")] = str
        # This is only needed if you want the some area but want the prices in a non local currency
        data_schema[vol.Optional("currency", default='')] = str
        data_schema[vol.Optional("VAT", default=True)] = bool
        data_schema[vol.Optional("precision", default=3)] = vol.Coerce(int)
        data_schema[vol.Optional("low_price_cutoff", default=1.0)] = vol.Coerce(float)
        data_schema[vol.Optional("price_type", default="kWh")] = str

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(data_schema), errors=self._errors
        )

    async def async_step_import(self, user_input):  # pylint: disable=unused-argument
        """Import a config entry.
        Special type of import, we're not actually going to store any data.
        Instead, we're going to rely on the values that are in config file.
        """
        _LOGGER.info('ass called async_step_import')
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        return self.async_create_entry(title="configuration.yaml", data={})
