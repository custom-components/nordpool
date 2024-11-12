"""Adds config flow for nordpool."""
import logging
import re
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.template import Template

if TYPE_CHECKING:
    from typing import Any, Mapping

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
        _config_entry = None

    async def async_step_user(
        self, user_input=None
    ):  # pylint: disable=dangerous-default-value
        """Handle a flow initialized by the user."""
        self._errors = {}

        if user_input is not None:
            template_ok = False
            self._patch_template(user_input["additional_costs"])

            template_ok = await self._valid_template(user_input["additional_costs"])
            if template_ok:
                return self.async_create_entry(title="Nordpool", data=user_input)
            else:
                self._errors["base"] = "invalid_template"

        return self.async_show_form(
            step_id="user",
            **self._get_form_data(user_input),
            errors=self._errors,
        )

    async def async_step_reconfigure(
        self, entry_data: "Mapping[str, Any]"
    ) -> config_entries.ConfigFlowResult:
        """Handle a reconfiguration flow initialized by the user."""
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self._config_entry = config_entry
        return await self.async_step_reconfigure_confirm()

    async def async_step_reconfigure_confirm(
        self, user_input: "dict[str, Any] | None" = None
    ) -> config_entries.ConfigFlowResult:
        """Handle a reconfiguration flow initialized by the user."""

        if user_input is not None:
            template_ok = False
            self._patch_template(user_input["additional_costs"])

            template_ok = await self._valid_template(user_input["additional_costs"])
            if template_ok:
                return self.async_create_entry(title="Nordpool", data=user_input)
            else:
                self._errors["base"] = "invalid_template"

            return self.async_update_reload_and_abort(
                self._config_entry,
                data=user_input,
                reason="reconfigure_successful",
            )

        return self.async_show_form(
            step_id="reconfigure_confirm", **self._get_form_data(self._config_entry.data),
            errors=self._errors
        )

    def _get_form_data(self, user_input: "Mapping[str, Any] | None"):
        """Populate form data from user input and default values"""
        if not user_input:
            user_input = dict()

        data_schema = vol.Schema({
            vol.Required("region", default=user_input.get("region", None)): vol.In(regions),
            vol.Required("currency", default=user_input.get("currency", None)): vol.In(currencys),
            vol.Optional("VAT", default=user_input.get("VAT", True)): bool,
            vol.Required("precision", default=user_input.get("precision", 3)): vol.Coerce(int),
            vol.Required("low_price_cutoff", default=user_input.get("low_price_cutoff", 1.0)): vol.Coerce(float),
            vol.Optional("price_in_cents", default=user_input.get("price_in_cents", False)): bool,
            vol.Required("price_type", default=user_input.get("price_type", "kWh")): vol.In(price_types),
            vol.Optional("additional_costs", default=user_input.get("additional_costs", "") or DEFAULT_TEMPLATE): str,
        })

        description_placeholders = {
            "price_type": price_types[0],
            "additional_costs": "{{0.0|float}}",
        }

        return dict(description_placeholders=description_placeholders, data_schema=data_schema)

    def _patch_template(self, user_template: str):
        """Fix common mistakes in template"""
        # Lets try to remove the most common mistakes, this will still fail if the template
        # was writte in notepad or something like that..
        user_template = re.sub(
            r"\s{2,}", "", user_template
        )

    async def _valid_template(self, user_template):
        """Validate template"""
        try:
            #
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
            pass
        return False

    async def async_step_import(self, user_input):  # pylint: disable=unused-argument
        """Import a config entry.
        Special type of import, we're not actually going to store any data.
        Instead, we're going to rely on the values that are in config file.
        """
        return self.async_create_entry(title="configuration.yaml", data={})
