import logging
from collections import defaultdict
from datetime import datetime, timedelta
from functools import partial
from random import randint
from typing import Union

import aiohttp
import backoff
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Config, HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.util import dt as dt_utils
from pytz import timezone

from .aio_price import AioPrices
from .events import async_track_time_change_in_tz
from .misc import test_valid_nordpooldata, stock, predicate

DOMAIN = "nordpool"
_LOGGER = logging.getLogger(__name__)
RANDOM_MINUTE = randint(0, 10)
RANDOM_SECOND = randint(0, 59)
EVENT_NEW_DATA = "nordpool_update_new_data"
_CURRENCY_LIST = ["DKK", "EUR", "NOK", "SEK"]

_REGIONS = {
    "DK1": ["DKK", "Denmark", 0.25],
    "DK2": ["DKK", "Denmark", 0.25],
    "FI": ["EUR", "Finland", 0.24],
    "EE": ["EUR", "Estonia", 0.20],
    "LT": ["EUR", "Lithuania", 0.21],
    "LV": ["EUR", "Latvia", 0.21],
    "Oslo": ["NOK", "Norway", 0.25],
    "Kr.sand": ["NOK", "Norway", 0.25],
    "Bergen": ["NOK", "Norway", 0.25],
    "Molde": ["NOK", "Norway", 0.25],
    "Tr.heim": ["NOK", "Norway", 0.25],
    "Tromsø": ["NOK", "Norway", 0.25],
    "SE1": ["SEK", "Sweden", 0.25],
    "SE2": ["SEK", "Sweden", 0.25],
    "SE3": ["SEK", "Sweden", 0.25],
    "SE4": ["SEK", "Sweden", 0.25],
    # What zone is this?
    "SYS": ["EUR", "System zone", 0.25],
    "FR": ["EUR", "France", 0.055],
    "NL": ["EUR", "Netherlands", 0.21],
    "BE": ["EUR", "Belgium", 0.21],
    "AT": ["EUR", "Austria", 0.20],
    # Tax is disabled for now, i need to split the areas
    # to handle the tax.
    "DE-LU": ["EUR", "Germany and Luxembourg", 0],
}


CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)
NAME = DOMAIN
VERSION = "0.0.5"
ISSUEURL = "https://github.com/custom-components/nordpool/issues"
STARTUP = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom component
If you have any issues with this you need to open an issue here:
{ISSUEURL}
-------------------------------------------------------------------
"""


class NordpoolData:
    """Handles the updates."""

    _areas = []

    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        self._last_tick = None
        self._data = defaultdict(dict)
        self.currency = []
        self.listeners = []

    @classmethod
    def add_area(cls, value):
        if value not in cls._areas:
            cls._areas.append(value)

    async def _update(self, *args, type_="today", dt=None) -> bool:
        _LOGGER.debug("calling _update %s %s", type_, dt)
        hass = self._hass
        client = async_get_clientsession(hass)

        if dt is None:
            dt = dt_utils.now()

        @backoff.on_predicate(backoff.expo, predicate=predicate, logger=_LOGGER)
        @backoff.on_exception(backoff.expo, aiohttp.ClientError, logger=_LOGGER)
        async def really_update(currency: str, end_date: datetime) -> Union[bool, None]:
            """Requests the data from nordpool and retries on http errors or missing/wrong data."""
            func_now = dt_utils.now()
            spot = AioPrices(currency, client)
            data = await spot.hourly(end_date=end_date)
            # We only verify the the areas that has the correct currency, example AT is always inf for all other currency then EUR
            # Now this will fail for any users that has a non local currency for the region they selected.
            # Thats a problem for another day..
            # If the user has multiple sensors in the same currency all of there data must be ok.
            regions_to_verify = self._areas or [
                k for k, v in _REGIONS.items() if v[0] == currency
            ]
            data_ok = test_valid_nordpooldata(data, region=regions_to_verify)

            if data_ok is False:
                np_should_have_released_new_data = stock(func_now).replace(
                    hour=13, minute=RANDOM_MINUTE, second=RANDOM_SECOND
                )

                if type_ == "tomorrow":
                    if stock(func_now) >= np_should_have_released_new_data:
                        _LOGGER.info(
                            "New data should be available, it does not exist or isnt valid so we will retry the request later"
                        )
                        return False

                    else:
                        _LOGGER.info("No new data is available")
                        # Need to handle the None
                        # Give up, a new request will pulling the data 1300ish
                        return None
                else:
                    return False

            else:
                self._data[currency][type_] = data["areas"]

            return True

        attempts = []
        for currency in self.currency:
            update_attempt = await really_update(currency, dt)
            attempts.append(update_attempt)

        return all(attempts)

    async def update_today(self, n: datetime) -> bool:
        """Gets the prices for today"""
        _LOGGER.debug("Updating todays prices.")
        return await self._update("today")

    async def update_tomorrow(self, n: datetime) -> bool:
        """Get the prices for tomorrow"""
        _LOGGER.debug("Updating tomorrows prices.")
        result = await self._update(
            type_="tomorrow", dt=dt_utils.now() + timedelta(hours=24)
        )
        return result

    async def _someday(self, area: str, currency: str, day: str) -> Union[dict, None]:
        """Returns todays or tomorrows prices in a area in the currency"""
        if currency not in _CURRENCY_LIST:
            raise ValueError(
                "%s is a invalid currency possible values are %s"
                % (currency, ", ".join(_CURRENCY_LIST))
            )

        # This is needed as the currency is
        # set in the sensor and we need to pull for the first time.
        if currency not in self.currency:
            self.currency.append(currency)
            await self.update_today(None)
            await self.update_tomorrow(None)

        return self._data.get(currency, {}).get(day, {}).get(area)

    async def today(self, area: str, currency: str) -> Union[dict, None]:
        """Returns todays prices in a area in the requested currency"""
        res = await self._someday(area, currency, "today")
        return res

    async def tomorrow(self, area: str, currency: str) -> Union[dict, None]:
        """Returns tomorrows prices in a area in the requested currency"""
        res = await self._someday(area, currency, "tomorrow")
        return res


async def _dry_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up using yaml config file."""

    if DOMAIN not in hass.data:
        api = NordpoolData(hass)
        hass.data[DOMAIN] = api

        async def new_day_cb(n) -> None:
            """Cb to handle some house keeping when it a new day."""
            _LOGGER.debug("Called new_day_cb callback")

            for curr in api.currency:
                tom = api._data[curr]["tomorrow"]
                regions_to_verify = [k for k, v in _REGIONS.items() if v[0] == curr]
                _LOGGER.debug("Checking that data we already have for tomorrow is ok.")
                data_ok = test_valid_nordpooldata(tom, region=regions_to_verify)
                if data_ok:
                    api._data[curr]["today"] = tom
                else:
                    await api.update_today(None)

                api._data[curr]["tomorrow"] = {}
                _LOGGER.debug(
                    "Clear tomorrow for %s, %s", curr, api._data[curr]["tomorrow"]
                )

            async_dispatcher_send(hass, EVENT_NEW_DATA)

        async def new_hr(n: datetime) -> None:
            """Callback to tell the sensors to update on a new hour."""
            _LOGGER.debug("Called new_hr callback")

            # We don't want to notify the sensor about this hour as this is
            # handled by the new_day_cb anyway.
            if n.hour == 0:
                return

            async_dispatcher_send(hass, EVENT_NEW_DATA)

        async def new_data_cb(n: datetime) -> None:
            """Callback to fetch new data for tomorrows prices at 1300ish CET
            and notify any sensors, about the new data
            """
            _LOGGER.debug("Called new_data_cb")
            await api.update_tomorrow(n)
            async_dispatcher_send(hass, EVENT_NEW_DATA)

        # Handles futures updates
        cb_update_tomorrow = async_track_time_change_in_tz(
            hass,
            new_data_cb,
            hour=13,
            minute=RANDOM_MINUTE,
            second=RANDOM_SECOND,
            tz=timezone("Europe/Stockholm"),
        )

        cb_new_day = async_track_time_change(
            hass, new_day_cb, hour=0, minute=0, second=0
        )

        cb_new_hr = async_track_time_change(hass, new_hr, minute=0, second=0)

        api.listeners.append(cb_update_tomorrow)
        api.listeners.append(cb_new_hr)
        api.listeners.append(cb_new_day)

    return True


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up using yaml config file."""
    return await _dry_setup(hass, config)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up nordpool as config entry."""
    res = await _dry_setup(hass, entry.data)
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )

    # entry.add_update_listener(async_reload_entry)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return res


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    if unload_ok:
        if DOMAIN in hass.data:
            for unsub in hass.data[DOMAIN].listeners:
                unsub()
            hass.data.pop(DOMAIN)

        return True

    return False


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
