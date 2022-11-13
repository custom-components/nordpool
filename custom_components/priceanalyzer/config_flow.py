"""Adds config flow for nordpool."""
import logging
import re

from typing import Optional

from copy import deepcopy
from types import MappingProxyType

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.template import is_template_string, Template

from . import DOMAIN
from .const import _PRICE_IN, _REGIONS, DEFAULT_TEMPLATE, HOT_WATER_CONFIG, HOT_WATER_DEFAULT_CONFIG, HOT_WATER_DEFAULT_CONFIG_JSON

regions = sorted(list(_REGIONS.keys()))
currencys = sorted(list(set(v[0] for k, v in _REGIONS.items())))
price_types = sorted(list(_PRICE_IN.keys()))

placeholders = {
    "region": regions,
    "currency": currencys,
    "price_type": price_types,
    "additional_costs": "{{0.01|float}}",
}

_LOGGER = logging.getLogger(__name__)



def get_schema(existing_config = None) -> dict:
    """Helper to get schema with editable default"""

    ec = existing_config

    if ec is None:
        ec = {}
    schema = {
        vol.Required("region", default=ec.get("region", None)): vol.In(regions),
        vol.Optional("currency", default=ec.get("currency", "")): vol.In(currencys),
        vol.Optional("VAT", default=ec.get("VAT", True)): bool,
        vol.Optional("precision", default=ec.get("precision", 3)): vol.Coerce(int),
        vol.Optional(
            "low_price_cutoff", default=ec.get("low_price_cutoff", 1.0)
        ): vol.Coerce(float),
        vol.Optional("price_in_cents", default=ec.get("price_in_cents", False)): bool,
        vol.Optional("price_type", default=ec.get("price_type", "kWh")): vol.In(
            price_types
        ),
        vol.Optional("additional_costs", default=ec.get("additional_costs", DEFAULT_TEMPLATE)): str,
        vol.Optional("pa_price_before_active", default=ec.get('pa_price_before_active',0.2)): float,        
        vol.Optional("percent_difference", default=ec.get("percent_difference",20)): int,
        vol.Optional("price_before_active", default=ec.get('price_before_active',0.2)): float,
        vol.Optional(HOT_WATER_CONFIG, default=ec.get(HOT_WATER_CONFIG, HOT_WATER_DEFAULT_CONFIG_JSON)): str,
    }
    return schema


class Base:
    """Simple helper"""

    async def _valid_template(self, user_template):
        try:
            _LOGGER.debug(user_template)
            ut = Template(user_template, self.hass).async_render(
                current_price=0,
            )  # Add current price as 0 as we dont know it yet..
            _LOGGER.debug("user_template %s value %s", user_template, ut)            
            if isinstance(ut, float):
                return True
            else:
                return False
        except Exception as e:
            _LOGGER.error(e)

        return False

    async def check_settings(self, user_input):
        template_ok = False
        if user_input is not None:
            if user_input["additional_costs"] in (None, ""):
                user_input["additional_costs"] = DEFAULT_TEMPLATE
            else:
                # Lets try to remove the most common mistakes, this will still fail if the template
                # was writte in notepad or something like that..
                user_input["additional_costs"] = re.sub(
                    r"\s{2,}", "", user_input["additional_costs"]
                )

            template_ok = await self._valid_template(user_input["additional_costs"])

        return template_ok, user_input


class PriceAnalyzerFlowHandler(Base, config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Nordpool."""

    VERSION = "1.0"
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
            template_ok, user_input = await self.check_settings(user_input)
            if template_ok:
                title = DOMAIN + user_input["region"]
                return self.async_create_entry(title=title, data=user_input)
            else:
                self._errors["base"] = "invalid_template"
        
        schema = get_schema(user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            description_placeholders=placeholders,
            errors=self._errors,
        )



    async def async_step_import(self, user_input):  # pylint: disable=unused-argument
        """Import a config entry.
        Special type of import, we're not actually going to store any data.
        Instead, we're going to rely on the values that are in config file.
        """
        return self.async_create_entry(title="configuration.yaml", data={})




    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the Options handler"""
        return PriceAnalyzerOptionsHandler(config_entry)


class PriceAnalyzerOptionsHandler(Base, config_entries.OptionsFlow):
    """Handles the options for the component"""

    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry
        # We dont really care about the options, this component allows all
        # settings to be edit after the sensor is created.
        # For this to work we need to have a stable entity id.
        self.options = dict(config_entry.data)
        # self.data = config_entries.data
        self._errors = {}

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_user(user_input=user_input)

    async def async_step_edit(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_user(user_input=user_input)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        _LOGGER.debug('Trying updating Integration for PA with options: %s', user_input)
        if user_input is not None:
            template_ok, user_input = await self.check_settings(user_input)
            if template_ok:
                title = DOMAIN + user_input["region"]
                _LOGGER.debug('updating Integration (template_ok) for %s with options: %s', title, user_input)
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=user_input, options=self.config_entry.options
                )
                return self.async_create_entry(title=title, data=user_input)
            else:
                self._errors["base"] = "invalid_template"

            self.options.update(user_input)
            title = DOMAIN + user_input["region"]
            _LOGGER.debug('updating Integration for %s with options i think: %s', title, user_input)
            return self.async_create_entry(title=title, data=self.options)

        # Get the current settings and use them as default.
        ds = get_schema(self.options)

        return self.async_show_form(
            step_id="edit",
            data_schema=vol.Schema(ds),
            description_placeholders=placeholders,
            errors={},
        )