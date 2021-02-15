"""Adds config flow for nordpool."""
import logging
import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.template import is_template_string

from . import DOMAIN
from .sensor import _PRICE_IN, _REGIONS, DEFAULT_TEMPLATE

regions = sorted(list(_REGIONS.keys()))
currencys = sorted(list(set(v[0] for k, v in _REGIONS.items())))
price_types = sorted(list(_PRICE_IN.keys()))
_LOGGER = logging.getLogger(__name__)


class NordpoolFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Nordpool."""

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
            if user_input["additional_costs"] == "":
                user_input["additional_costs"] = DEFAULT_TEMPLATE
            else:
                # Lets try to remove the most common mistakes, this will still fail if the template
                # was writte in notepad or something like that..
                user_input["additional_costs"] = re.sub(r"\s{2,}", '', user_input["additional_costs"])
                if not is_template_string(user_input["additional_costs"]):
                    raise

            return self.async_create_entry(title="Nordpool", data=user_input)

        data_schema = {
            vol.Required("region", default=None): vol.In(regions),
            vol.Optional("friendly_name", default=""): str,
            vol.Optional("currency", default=""): vol.In(currencys),
            vol.Optional("VAT", default=True): bool,
            vol.Optional("precision", default=3): vol.Coerce(int),
            vol.Optional("low_price_cutoff", default=1.0): vol.Coerce(float),
            vol.Optional("price_in_cents", default=False): bool,
            vol.Optional("price_type", default="kWh"): vol.In(price_types),
            vol.Optional("additional_costs", default=""): str
        }

        placeholders = {
            "region": regions,
            "currency": currencys,
            "price_type": price_types,
            "additional_costs": "{{0}}"
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            description_placeholders=placeholders,
            errors=self._errors,
        )

    async def async_step_import(self, user_input):  # pylint: disable=unused-argument
        """Import a config entry.
        Special type of import, we're not actually going to store any data.
        Instead, we're going to rely on the values that are in config file.
        """
        return self.async_create_entry(title="configuration.yaml", data={})
