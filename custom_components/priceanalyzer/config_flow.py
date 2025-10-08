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
from jinja2 import pass_context
from homeassistant.util import dt as dt_utils

from . import DOMAIN
from .const import (_PRICE_IN, _REGIONS, DEFAULT_TEMPLATE, DEFAULT_TIME_RESOLUTION, HOT_WATER_CONFIG, HOT_WATER_DEFAULT_CONFIG, 
                   HOT_WATER_DEFAULT_CONFIG_JSON, TEMP_DEFAULT, TEMP_FIVE_MOST_EXPENSIVE, TEMP_IS_FALLING,
                   TEMP_FIVE_CHEAPEST, TEMP_TEN_CHEAPEST, TEMP_LOW_PRICE, TEMP_NOT_CHEAP_NOT_EXPENSIVE, TEMP_MINIMUM)

regions = sorted(list(_REGIONS.keys()))
currencys = sorted(list(set(v[0] for k, v in _REGIONS.items())))
price_types = sorted(list(_PRICE_IN.keys()))
time_resolutions = ["quarterly", "hourly"]

placeholders = {
    "region": regions,
    "currency": currencys,
    "price_type": price_types,
    "additional_costs": "{{0.01|float}}",
}

_LOGGER = logging.getLogger(__name__)


def _migrate_hot_water_config(existing_config):
    """Migrate existing JSON hot water config to individual fields"""
    if existing_config is None:
        return {}
    
    # If we have individual fields already, return as-is
    if any(key.startswith('temp_') for key in existing_config.keys()):
        return existing_config
    
    # Migrate from JSON config
    migrated = existing_config.copy()
    hot_water_json = existing_config.get(HOT_WATER_CONFIG)
    
    if hot_water_json:
        try:
            import json
            hot_water_dict = json.loads(hot_water_json) if isinstance(hot_water_json, str) else hot_water_json
            
            # Map JSON keys to individual config keys
            migrated['temp_default'] = hot_water_dict.get(TEMP_DEFAULT, HOT_WATER_DEFAULT_CONFIG[TEMP_DEFAULT])
            migrated['temp_five_most_expensive'] = hot_water_dict.get(TEMP_FIVE_MOST_EXPENSIVE, HOT_WATER_DEFAULT_CONFIG[TEMP_FIVE_MOST_EXPENSIVE])
            migrated['temp_is_falling'] = hot_water_dict.get(TEMP_IS_FALLING, HOT_WATER_DEFAULT_CONFIG[TEMP_IS_FALLING])
            migrated['temp_five_cheapest'] = hot_water_dict.get(TEMP_FIVE_CHEAPEST, HOT_WATER_DEFAULT_CONFIG[TEMP_FIVE_CHEAPEST])
            migrated['temp_ten_cheapest'] = hot_water_dict.get(TEMP_TEN_CHEAPEST, HOT_WATER_DEFAULT_CONFIG[TEMP_TEN_CHEAPEST])
            migrated['temp_low_price'] = hot_water_dict.get(TEMP_LOW_PRICE, HOT_WATER_DEFAULT_CONFIG[TEMP_LOW_PRICE])
            migrated['temp_not_cheap_not_expensive'] = hot_water_dict.get(TEMP_NOT_CHEAP_NOT_EXPENSIVE, HOT_WATER_DEFAULT_CONFIG[TEMP_NOT_CHEAP_NOT_EXPENSIVE])
            migrated['temp_minimum'] = hot_water_dict.get(TEMP_MINIMUM, HOT_WATER_DEFAULT_CONFIG[TEMP_MINIMUM])
            
            # Remove old JSON config
            migrated.pop(HOT_WATER_CONFIG, None)
        except (json.JSONDecodeError, TypeError):
            # If JSON parsing fails, use defaults
            pass
    
    return migrated

def get_schema(existing_config = None) -> dict:
    """Helper to get schema with editable default"""

    ec = _migrate_hot_water_config(existing_config)

    if ec is None:
        ec = {}
    schema = {
        vol.Required("region", default=ec.get("region", None)): vol.In(regions),
        vol.Optional("currency", default=ec.get("currency", "")): vol.In(currencys),
        vol.Optional("VAT", default=ec.get("VAT", True)): bool,
        vol.Optional("low_price_cutoff", default=ec.get("low_price_cutoff", 1.0)): vol.Coerce(float),
        vol.Optional("price_in_cents", default=ec.get("price_in_cents", False)): bool,
        vol.Optional("price_type", default=ec.get("price_type", "kWh")): vol.In(price_types),
        vol.Optional("time_resolution", default=ec.get("time_resolution", DEFAULT_TIME_RESOLUTION)): vol.In(time_resolutions),
        vol.Optional("additional_costs", default=ec.get("additional_costs", DEFAULT_TEMPLATE)): str,
        vol.Optional("multiply_template", default=ec.get("multiply_template", '{{correction * 1}}')): str,
        vol.Optional("hours_to_boost", default=ec.get("hours_to_boost", 2)): int,
        vol.Optional("hours_to_save", default=ec.get("hours_to_save", 2)): int,
        vol.Optional("pa_price_before_active", default=ec.get('pa_price_before_active',0.2)): float,
        vol.Optional("percent_difference", default=ec.get("percent_difference",20)): int,
        vol.Optional("price_before_active", default=ec.get('price_before_active',0.2)): float,
        # Individual hot water temperature settings
        vol.Optional("temp_default", default=ec.get('temp_default', HOT_WATER_DEFAULT_CONFIG[TEMP_DEFAULT])): vol.Coerce(float),
        vol.Optional("temp_five_most_expensive", default=ec.get('temp_five_most_expensive', HOT_WATER_DEFAULT_CONFIG[TEMP_FIVE_MOST_EXPENSIVE])): vol.Coerce(float),
        vol.Optional("temp_is_falling", default=ec.get('temp_is_falling', HOT_WATER_DEFAULT_CONFIG[TEMP_IS_FALLING])): vol.Coerce(float),
        vol.Optional("temp_five_cheapest", default=ec.get('temp_five_cheapest', HOT_WATER_DEFAULT_CONFIG[TEMP_FIVE_CHEAPEST])): vol.Coerce(float),
        vol.Optional("temp_ten_cheapest", default=ec.get('temp_ten_cheapest', HOT_WATER_DEFAULT_CONFIG[TEMP_TEN_CHEAPEST])): vol.Coerce(float),
        vol.Optional("temp_low_price", default=ec.get('temp_low_price', HOT_WATER_DEFAULT_CONFIG[TEMP_LOW_PRICE])): vol.Coerce(float),
        vol.Optional("temp_not_cheap_not_expensive", default=ec.get('temp_not_cheap_not_expensive', HOT_WATER_DEFAULT_CONFIG[TEMP_NOT_CHEAP_NOT_EXPENSIVE])): vol.Coerce(float),
        vol.Optional("temp_minimum", default=ec.get('temp_minimum', HOT_WATER_DEFAULT_CONFIG[TEMP_MINIMUM])): vol.Coerce(float),
    }
    return schema


class Base:
    """Simple helper"""

    async def _valid_template(self, user_template):
        try:
            def faker():
                def inner(*_, **__):
                    return dt_utils.now()
                return pass_context(inner)
            _LOGGER.debug(user_template)
            ut = Template(user_template, self.hass).async_render(
                current_price=200
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