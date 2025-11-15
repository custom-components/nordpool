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

def get_basic_schema(existing_config = None) -> dict:
    """Schema for basic setup step"""
    ec = existing_config if existing_config else {}
    return {
        vol.Optional("friendly_name", default=ec.get("friendly_name", "")): str,
        vol.Required("region", default=ec.get("region", None)): vol.In(regions),
        vol.Optional("currency", default=ec.get("currency", "")): vol.In(currencys),
        vol.Optional("VAT", default=ec.get("VAT", True)): bool,
        vol.Optional("time_resolution", default=ec.get("time_resolution", DEFAULT_TIME_RESOLUTION)): vol.In(time_resolutions),
    }

def get_price_schema(existing_config = None) -> dict:
    """Schema for price settings step"""
    ec = existing_config if existing_config else {}
    return {
        vol.Optional("price_type", default=ec.get("price_type", "kWh")): vol.In(price_types),
        vol.Optional("price_in_cents", default=ec.get("price_in_cents", False)): bool,
        vol.Optional("low_price_cutoff", default=ec.get("low_price_cutoff", 1.0)): vol.Coerce(float),
        vol.Optional("additional_costs", default=ec.get("additional_costs", DEFAULT_TEMPLATE)): str,
    }

def get_advanced_schema(existing_config = None) -> dict:
    """Schema for advanced settings step"""
    ec = existing_config if existing_config else {}
    return {
        vol.Optional("multiply_template", default=ec.get("multiply_template", '{{correction * 1}}')): str,
        vol.Optional("hours_to_boost", default=ec.get("hours_to_boost", 2)): int,
        vol.Optional("hours_to_save", default=ec.get("hours_to_save", 2)): int,
        vol.Optional("pa_price_before_active", default=ec.get('pa_price_before_active',0.2)): float,
        vol.Optional("percent_difference", default=ec.get("percent_difference",20)): int,
        vol.Optional("price_before_active", default=ec.get('price_before_active',0.2)): float,
    }

def get_hot_water_schema(existing_config = None) -> dict:
    """Schema for hot water temperature settings step"""
    ec = _migrate_hot_water_config(existing_config)
    if ec is None:
        ec = {}
    return {
        vol.Optional("temp_default", default=ec.get('temp_default', HOT_WATER_DEFAULT_CONFIG[TEMP_DEFAULT])): vol.Coerce(float),
        vol.Optional("temp_five_most_expensive", default=ec.get('temp_five_most_expensive', HOT_WATER_DEFAULT_CONFIG[TEMP_FIVE_MOST_EXPENSIVE])): vol.Coerce(float),
        vol.Optional("temp_is_falling", default=ec.get('temp_is_falling', HOT_WATER_DEFAULT_CONFIG[TEMP_IS_FALLING])): vol.Coerce(float),
        vol.Optional("temp_five_cheapest", default=ec.get('temp_five_cheapest', HOT_WATER_DEFAULT_CONFIG[TEMP_FIVE_CHEAPEST])): vol.Coerce(float),
        vol.Optional("temp_ten_cheapest", default=ec.get('temp_ten_cheapest', HOT_WATER_DEFAULT_CONFIG[TEMP_TEN_CHEAPEST])): vol.Coerce(float),
        vol.Optional("temp_low_price", default=ec.get('temp_low_price', HOT_WATER_DEFAULT_CONFIG[TEMP_LOW_PRICE])): vol.Coerce(float),
        vol.Optional("temp_not_cheap_not_expensive", default=ec.get('temp_not_cheap_not_expensive', HOT_WATER_DEFAULT_CONFIG[TEMP_NOT_CHEAP_NOT_EXPENSIVE])): vol.Coerce(float),
        vol.Optional("temp_minimum", default=ec.get('temp_minimum', HOT_WATER_DEFAULT_CONFIG[TEMP_MINIMUM])): vol.Coerce(float),
    }

def get_schema(existing_config = None) -> dict:
    """Helper to get complete schema with editable defaults (for backward compatibility)"""
    ec = _migrate_hot_water_config(existing_config)
    if ec is None:
        ec = {}
    
    # Combine all schemas for backward compatibility
    schema = {}
    schema.update(get_basic_schema(ec))
    schema.update(get_price_schema(ec))
    schema.update(get_advanced_schema(ec))
    schema.update(get_hot_water_schema(ec))
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
    """Config flow for PriceAnalyzer."""

    VERSION = "1.0"

    def __init__(self):
        """Initialize."""
        self._errors = {}
        self._data = {}

    async def async_step_user(
        self, user_input=None
    ):  # pylint: disable=dangerous-default-value
        """Handle a flow initialized by the user - Step 1: Basic Setup."""
        self._errors = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_config_menu()

        schema = get_basic_schema(self._data)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            description_placeholders=placeholders,
            errors=self._errors,
        )

    async def async_step_config_menu(self, user_input=None):
        """Show configuration menu."""
        return self.async_show_menu(
            step_id="config_menu",
            menu_options=["price_settings", "advanced_settings", "hot_water", "finish"],
        )

    async def async_step_price_settings(self, user_input=None):
        """Handle Step 2: Price Settings."""
        self._errors = {}

        if user_input is not None:
            # Validate template
            template_ok, validated_input = await self.check_settings(user_input)
            if not template_ok:
                self._errors["base"] = "invalid_template"
            else:
                self._data.update(validated_input)
                return await self.async_step_config_menu()

        schema = get_price_schema(self._data)

        return self.async_show_form(
            step_id="price_settings",
            data_schema=vol.Schema(schema),
            description_placeholders=placeholders,
            errors=self._errors,
        )

    async def async_step_advanced_settings(self, user_input=None):
        """Handle Step 3: Advanced Settings."""
        self._errors = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_config_menu()

        schema = get_advanced_schema(self._data)

        return self.async_show_form(
            step_id="advanced_settings",
            data_schema=vol.Schema(schema),
            description_placeholders=placeholders,
            errors=self._errors,
        )

    async def async_step_hot_water(self, user_input=None):
        """Handle Step 4: Hot Water Configuration."""
        self._errors = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_config_menu()

        schema = get_hot_water_schema(self._data)

        return self.async_show_form(
            step_id="hot_water",
            data_schema=vol.Schema(schema),
            description_placeholders=placeholders,
            errors=self._errors,
        )

    async def async_step_finish(self, user_input=None):
        """Finish configuration and create entry."""
        if "region" not in self._data:
            return await self.async_step_user()
        
        # Use friendly_name if provided, otherwise create default title
        if self._data.get("friendly_name") and self._data["friendly_name"].strip():
            title = self._data["friendly_name"]
        else:
            # Create unique title by checking for existing entries with same region
            base_title = DOMAIN + " " + self._data["region"]
            title = base_title
            existing_entries = self._async_current_entries()
            region_count = sum(1 for entry in existing_entries if entry.data.get("region") == self._data["region"])
            if region_count > 0:
                title = f"{base_title} #{region_count + 1}"
        
        return self.async_create_entry(title=title, data=self._data)



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
        # Note: self.config_entry is automatically set by the parent class
        # We dont really care about the options, this component allows all
        # settings to be edit after the sensor is created.
        # For this to work we need to have a stable entity id.
        self.options = dict(config_entry.data)
        self._errors = {}
        self._data = dict(config_entry.data)

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_options_menu(user_input=user_input)

    async def async_step_options_menu(self, user_input=None):
        """Show options menu."""
        return self.async_show_menu(
            step_id="options_menu",
            menu_options=["basic_setup", "price_settings", "advanced_settings", "hot_water", "finish"],
        )

    async def async_step_basic_setup(self, user_input=None):
        """Handle Step 1: Basic Setup."""
        self._errors = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_options_menu()

        schema = get_basic_schema(self._data)

        return self.async_show_form(
            step_id="basic_setup",
            data_schema=vol.Schema(schema),
            description_placeholders=placeholders,
            errors=self._errors,
        )

    async def async_step_price_settings(self, user_input=None):
        """Handle Step 2: Price Settings."""
        self._errors = {}

        if user_input is not None:
            # Validate template
            template_ok, validated_input = await self.check_settings(user_input)
            if not template_ok:
                self._errors["base"] = "invalid_template"
            else:
                self._data.update(validated_input)
                return await self.async_step_options_menu()

        schema = get_price_schema(self._data)

        return self.async_show_form(
            step_id="price_settings",
            data_schema=vol.Schema(schema),
            description_placeholders=placeholders,
            errors=self._errors,
        )

    async def async_step_advanced_settings(self, user_input=None):
        """Handle Step 3: Advanced Settings."""
        self._errors = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_options_menu()

        schema = get_advanced_schema(self._data)

        return self.async_show_form(
            step_id="advanced_settings",
            data_schema=vol.Schema(schema),
            description_placeholders=placeholders,
            errors=self._errors,
        )

    async def async_step_hot_water(self, user_input=None):
        """Handle Step 4: Hot Water Configuration."""
        self._errors = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_options_menu()

        schema = get_hot_water_schema(self._data)

        return self.async_show_form(
            step_id="hot_water",
            data_schema=vol.Schema(schema),
            description_placeholders=placeholders,
            errors=self._errors,
        )

    async def async_step_finish(self, user_input=None):
        """Finish configuration and save changes."""
        # Use friendly_name if provided, otherwise keep original title
        if self._data.get("friendly_name") and self._data["friendly_name"].strip():
            title = self._data["friendly_name"]
        else:
            title = self.config_entry.title
        
        _LOGGER.debug('updating Integration for %s with options: %s', title, self._data)
        self.hass.config_entries.async_update_entry(
            self.config_entry, data=self._data, title=title, options=self.config_entry.options
        )
        return self.async_create_entry(title="", data={})