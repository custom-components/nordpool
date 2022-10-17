"""Adds config flow for nordpool."""
import logging
import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from homeassistant.helpers.template import is_template_string, Template

from . import DOMAIN
from .const import _PRICE_IN, _REGIONS, DEFAULT_TEMPLATE, HOT_WATER_CONFIG, HOT_WATER_DEFAULT_CONFIG, HOT_WATER_DEFAULT_CONFIG_JSON

regions = sorted(list(_REGIONS.keys()))
currencys = sorted(list(set(v[0] for k, v in _REGIONS.items())))
price_types = sorted(list(_PRICE_IN.keys()))
_LOGGER = logging.getLogger(__name__)


class PriceAnalyzerFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
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
            template_ok = False
            if user_input["additional_costs"] in (None, ""):
                user_input["additional_costs"] = DEFAULT_TEMPLATE
            else:
                # Lets try to remove the most common mistakes, this will still fail if the template
                # was writte in notepad or something like that..
                user_input["additional_costs"] = re.sub(
                    r"\s{2,}", "", user_input["additional_costs"]
                )

            template_ok = await self._valid_template(user_input["additional_costs"])
            if template_ok:
                return self.async_create_entry(title="Price Analyzer" + user_input["region"], data=user_input)
            else:
                self._errors["base"] = "invalid_template"

        data_schema = {
            vol.Required("region", default=None): vol.In(regions),
            vol.Optional("currency", default=""): vol.In(currencys),
            vol.Optional("VAT", default=True): bool,
            vol.Optional("precision", default=3): vol.Coerce(int),
            vol.Optional("low_price_cutoff", default=1.0): vol.Coerce(float),
            vol.Optional("price_in_cents", default=False): bool,
            vol.Optional("price_type", default="kWh"): vol.In(price_types),
            vol.Optional("additional_costs", default="{{0.01|float}}"): str,
            vol.Optional("percent_difference", default=20): int,
            vol.Optional(HOT_WATER_CONFIG, default=HOT_WATER_DEFAULT_CONFIG_JSON): str,
        }

        placeholders = {
            "region": regions,
            "currency": currencys,
            "price_type": price_types,
            "additional_costs": "{{0.01|float}}",
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            description_placeholders=placeholders,
            errors=self._errors,
        )



    # @staticmethod
    # @callback
    # def async_get_options_flow(config_entry):
    #     return PriceAnalyzerEditFlow(config_entry)

    async def _valid_template(self, user_template):
        try:
            _LOGGER.debug(user_template)
            ut = Template(user_template, self.hass).async_render()
            if isinstance(ut, float):
                return True
            else:
                return False
        except Exception as e:
            _LOGGER.error(e)
            pass
        return False

    async def async_step_import(self, user_input):  # pylint: disable=unused-argument
        """Import a config entry.
        Special type of import, we're not actually going to store any data.
        Instead, we're going to rely on the values that are in config file.
        """
        return self.async_create_entry(title="configuration.yaml", data={})



# class PriceAnalyzerEditFlow(config_entries.OptionsFlow):
#     def __init__(self, config_entry):
#         self.config_entry = config_entry

#     async def async_step_init(self, user_input=None):
#         """Handle a flow initialized by the user."""
#         if user_input is not None:
#             return self.async_create_entry(title="", data=user_input)

#         schema = {
#             vol.Required("region", default=self.config_entry.data["region"]): vol.In(regions),
#             vol.Optional("currency", default=self.config_entry.data["currency"]): vol.In(currencys),
#             vol.Optional("VAT", default=self.config_entry.data["VAT"]): bool,
#             vol.Optional("precision", default=self.config_entry.data["precision"]): vol.Coerce(int),
#             vol.Optional("low_price_cutoff", default=self.config_entry.data["low_price_cutoff"]): vol.Coerce(float),
#             vol.Optional("price_in_cents", default=self.config_entry.data["price_in_cents"]): bool,
#             vol.Optional("price_type", default=self.config_entry.data["price_type"]): vol.In(price_types),
#             vol.Optional("additional_costs", default=self.config_entry.data["additional_costs"]): str,
#             vol.Optional("percent_difference", default=self.config_entry.data["percent_difference"]): int,
#         }

#         return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
