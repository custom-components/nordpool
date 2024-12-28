import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send


_LOGGER = logging.getLogger(__name__)


DO_ACITON_SCHEMA = vol.Schema(
    {vol.Optional("currency"): str, vol.Optional("something"): str}
)


async def async_setup_services(hass: HomeAssistant):
    _LOGGER.debug("Setting up services")
    hass.services.async_register("NORDPOOL", DO_ACITON_SCHEMA, do_action)


async def do_action(hass: HomeAssistant, service_call: ServiceCall):
    _LOGGER.debug("called do_action with %s" % service_call)
    api = hass.data.get("NORDPOOL")
    if api:
        data = await api.monthly()
        print(data)
