import logging

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from .const import _REGIONS, DEFAULT_TEMPLATE


_LOGGER = logging.getLogger(__name__)


def check(values):
    return any([i for i in values if i in list(_REGIONS.keys())])


def check2(value):
    def validator(value):
        c = any([i for i in value if i in list(_REGIONS.keys())])
        if c is not True:
            vol.Invalid("ERRRR")
        print(value)
        return value

    return validator


HOURLY_SCHEMA = vol.Schema(
    {
        vol.Required("currency"): str,
        vol.Required("date"): cv.date,
        vol.Required("area"): check2(cv.ensure_list),
    }
)


YEAR_SCHEMA = vol.Schema(
    {
        vol.Required("currency"): str,
        vol.Required("year"): cv.matches_regex(r"^[1|2]\d{3}$"),
        vol.Required("area"): check2(cv.ensure_list),
        vol.Optional("template"): str,
    }
)


async def async_setup_services(hass: HomeAssistant):
    _LOGGER.debug("Setting up services")
    from .aio_price import AioPrices

    client = async_get_clientsession(hass)

    async def hourly(service_call: ServiceCall) -> Any:
        sc = service_call.data
        _LOGGER.debug("called hourly with %r", sc)

        return await AioPrices(sc["currency"], client).hourly(
            areas=sc["area"], end_date=sc["date"]
        )

    async def yearly(service_call: ServiceCall):
        sc = service_call.data
        _LOGGER.debug("called hourly with %r", sc)

        value = await AioPrices(sc["currency"], client).yearly(
            areas=sc["area"], end_date=sc["year"]
        )
        print(value)

        t = cv.template(sc["template"]).async_render_with_possible_json_value(
            value, parse_result=True
        )
        print(t)

        return ""

    async def monthly(service_call: ServiceCall):
        sc = service_call.data
        _LOGGER.debug("called monthly with %r", sc)

        return await AioPrices(sc["currency"], client).monthly(
            areas=sc["area"], end_date=sc["year"]
        )

    async def daily(service_call: ServiceCall):
        sc = service_call.data
        _LOGGER.debug("called daily with %r", sc)

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
