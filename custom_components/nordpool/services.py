import logging
from datetime import datetime

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.util import dt as dt_util

from .const import _REGIONS


_LOGGER = logging.getLogger(__name__)


def check_setting(value):
    def validator(value):
        c = any([i for i in value if i in list(_REGIONS.keys())])
        if c is not True:
            vol.Invalid(
                f"{value} in not in on of the supported areas {','.join(_REGIONS.keys())}"
            )
        return value

    return validator


HOURLY_SCHEMA = vol.Schema(
    {
        vol.Required("currency"): str,
        vol.Required("date"): cv.date,
        vol.Required("area"): check_setting(cv.ensure_list),
    }
)


YEAR_SCHEMA = vol.Schema(
    {
        vol.Required("currency"): str,
        vol.Required("year", default=dt_util.now().strftime("Y")): cv.matches_regex(
            r"^[1|2]\d{3}$"
        ),
        vol.Required("area"): check_setting(cv.ensure_list),
    }
)


async def async_setup_services(hass: HomeAssistant):
    _LOGGER.debug("Setting up services")
    from .aio_price import AioPrices

    client = async_get_clientsession(hass)

    async def hourly(service_call: ServiceCall) -> Any:
        sc = service_call.data
        _LOGGER.debug("called hourly with %r", sc)

        # Convert the date to datetime as the rest of the code expects a datetime. We will want to keep date as it easier for ppl to use.
        end_date = datetime(
            year=sc["date"].year, month=sc["date"].month, day=sc["date"].day
        )

        value = await AioPrices(sc["currency"], client).hourly(
            areas=sc["area"], end_date=end_date, raw=True
        )

        _LOGGER.debug("Got value %r", value)
        return value

    async def yearly(service_call: ServiceCall):
        sc = service_call.data
        _LOGGER.debug("called yearly with %r", sc)

        value = await AioPrices(sc["currency"], client).yearly(
            areas=sc["area"], end_date=sc["year"]
        )

        _LOGGER.debug("Got value %r", value)
        return value

    async def weekly(service_call: ServiceCall):
        sc = service_call.data
        _LOGGER.debug("called weekly with %r", sc)

        value = await AioPrices(sc["currency"], client).yearly(
            areas=sc["area"], end_date=sc["year"]
        )

        _LOGGER.debug("Got value %r", value)
        return value

    async def monthly(service_call: ServiceCall):
        sc = service_call.data
        _LOGGER.debug("called monthly with %r", sc)

        value = await AioPrices(sc["currency"], client).monthly(
            areas=sc["area"], end_date=sc["year"]
        )
        _LOGGER.debug("Got value %r", value)
        return value

    async def daily(service_call: ServiceCall):
        sc = service_call.data
        _LOGGER.debug("called daily with %r", sc)

        value = await AioPrices(sc["currency"], client).daily(
            areas=sc["area"], end_date=sc["year"]
        )
        _LOGGER.debug("Got value %r", value)
        return value

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
    hass.services.async_register(
        domain="nordpool",
        service="weekly",
        service_func=weekly,
        schema=YEAR_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
