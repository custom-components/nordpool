import logging

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from .const import _REGIONS


_LOGGER = logging.getLogger(__name__)


HOURLY_SCHEMA = vol.Schema(
    {
        vol.Required("currency"): str,
        vol.Required("date"): cv.date,
        vol.Required("area"): vol.In(list(_REGIONS.keys())),
    }
)


YEAR_SCHEMA = vol.Schema(
    {
        vol.Required("currency"): str,
        vol.Required("year"): cv.matches_regex(r"^[1|2]\d{3}$"),
        vol.Required("area"): vol.ensure_list,
    }
)


async def async_setup_services(hass: HomeAssistant):
    _LOGGER.debug("Setting up services")
    from .aio_price import AioPrices

    client = async_get_clientsession(hass)

    async def hourly(service_call: ServiceCall) -> Any:
        sc = service_call.data

        return await AioPrices(sc["currency"], client).hourly(
            areas=sc["area"], end_date=sc["date"]
        )

    async def yearly(service_call: ServiceCall):
        sc = service_call.data
        return await AioPrices(sc["currency"], client).yearly(
            areas=sc["area"], end_date=sc["year"]
        )

    async def monthly(service_call: ServiceCall):
        sc = service_call.data
        return await AioPrices(sc["currency"], client).monthly(
            areas=sc["area"], end_date=sc["year"]
        )

    async def daily(service_call: ServiceCall):
        sc = service_call.data
        return await AioPrices(sc["currency"], client).daily(
            areas=sc["area"], end_date=sc["year"]
        )

    hass.services.async_register(
        domain="nordpool",
        service="hourly",
        service_func=hourly,
        schema=HOURLY_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        domain="nordpool",
        service="yearly",
        service_func=yearly,
        schema=YEAR_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        domain="nordpool",
        service="monthly",
        service_func=monthly,
        schema=YEAR_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        domain="nordpool",
        service="daily",
        service_func=daily,
        schema=YEAR_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
