"""Adds config flow for nordpool."""
from collections import OrderedDict

import voluptuous as vol
from homeassistant import config_entries

from . import DOMAIN


@config_entries.HANDLERS.register(DOMAIN)
class BlueprintFlowHandler(config_entries.ConfigFlow):
    """Config flow for Blueprint."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def async_step_user(
        self, user_input=None
    ):  # pylint: disable=dangerous-default-value
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            return self.async_create_entry(title="Elspot", data=user_input)

        return await self._show_config_form(user_input)

    async def _show_config_form(self, user_input):
        """Show the configuration form to edit location data."""
        data_schema = OrderedDict()
        data_schema[vol.Required("region", default="Kr.sand")] = str
        data_schema[vol.Optional("friendly_name", default="")] = str
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
        return self.async_create_entry(title="configuration.yaml", data={})
