import logging
from collections import defaultdict
from datetime import timedelta
from random import randint

import backoff
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_utils

from .aio_price import AioPrices, InvalidValueException
from .events import async_track_time_change_in_tz

DOMAIN = "nordpool"
_LOGGER = logging.getLogger(__name__)
RANDOM_MINUTE = randint(10, 30)
RANDOM_SECOND = randint(0, 59)
EVENT_NEW_HOUR = "nordpool_update_hour"
EVENT_NEW_DAY = "nordpool_update_day"
EVENT_NEW_PRICE = "nordpool_update_new_price"
SENTINEL = object()

_CURRENCY_LIST = ["DKK", "EUR", "NOK", "SEK"]


CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)


NAME = DOMAIN
VERSION = "0.0.16"
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

PLATFORMS: list[Platform] = [Platform.SENSOR]


class NordpoolData:
    """Holds the data"""

    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        self._last_tick = None
        self._data = defaultdict(dict)
        self.currency = []
        self.listeners = []
        self.areas = []

    async def _update(self, type_="today", dt=None, areas=None):
        _LOGGER.debug("calling _update %s %s %s", type_, dt, areas)
        hass = self._hass
        client = async_get_clientsession(hass)

        if dt is None:
            dt = dt_utils.now()

        if areas is not None:
            self.areas += [area for area in areas if area not in self.areas]
        # We dont really need today and morrow
        # when the region is in another timezone
        # as we request data for 3 days anyway.
        # Keeping this for now, but this should be changed.
        for currency in self.currency:
            spot = AioPrices(currency, client)
            data = await spot.hourly(end_date=dt, areas=self.areas if len(self.areas) > 0 else None)
            if data:
                self._data[currency][type_] = data["areas"]

    async def update_today(self, areas=None):
        """Update today's prices"""
        _LOGGER.debug("Updating today's prices.")
        if areas is not None:
            self.areas += [area for area in areas if area not in self.areas]
        await self._update("today", areas=self.areas if len(self.areas) > 0 else None)

    async def update_tomorrow(self, areas=None):
        """Update tomorrows prices."""
        _LOGGER.debug("Updating tomorrows prices.")
        if areas is not None:
            self.areas += [area for area in areas if area not in self.areas]
        await self._update(type_="tomorrow", dt=dt_utils.now() + timedelta(hours=24), areas=self.areas if len(self.areas) > 0 else None)

    async def _someday(self, area: str, currency: str, day: str):
        """Returns today's or tomorrow's prices in an area in the currency"""
        if currency not in _CURRENCY_LIST:
            raise ValueError(
                "%s is an invalid currency, possible values are %s"
                % (currency, ", ".join(_CURRENCY_LIST))
            )

        if area not in self.areas:
            self.areas.append(area);
        # This is needed as the currency is
        # set in the sensor.
        if currency not in self.currency:
            self.currency.append(currency)
            try:
                await self.update_today(areas=self.areas)
            except InvalidValueException:
                _LOGGER.debug("No data available for today, retrying later")
            try:
                await self.update_tomorrow(areas=self.areas)
            except InvalidValueException:
                _LOGGER.debug("No data available for tomorrow, retrying later")

            # Send a new data request after new data is updated for this first run
            # This way if the user has multiple sensors they will all update
            async_dispatcher_send(self._hass, EVENT_NEW_HOUR)

        return self._data.get(currency, {}).get(day, {}).get(area)

    async def today(self, area: str, currency: str) -> dict:
        """Returns today's prices in an area in the requested currency"""
        return await self._someday(area, currency, "today")
        

    async def tomorrow(self, area: str, currency: str):
        """Returns tomorrow's prices in an area in the requested currency"""
        return await self._someday(area, currency, "tomorrow")
        

async def _dry_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up using yaml config file."""
    if DOMAIN not in hass.data:
        api = NordpoolData(hass)
        hass.data[DOMAIN] = api
        _LOGGER.debug("Added %s to hass.data", DOMAIN)

        async def new_day_cb(_):
            """Cb to handle some house keeping when it a new day."""
            _LOGGER.debug("Called new_day_cb callback")

            for curr in api.currency:
                if not api._data.get(curr, {}).get("tomorrow"):
                    api._data[curr]["today"] = await api.update_today()
                else:
                    api._data[curr]["today"] = api._data[curr]["tomorrow"]
                api._data[curr]["tomorrow"] = {}

            async_dispatcher_send(hass, EVENT_NEW_DAY)

        async def new_hr(_):
            """Callback to tell the sensors to update on a new hour."""
            _LOGGER.debug("Called new_hr callback")
            async_dispatcher_send(hass, EVENT_NEW_HOUR)

        @backoff.on_exception(
            backoff.constant,
            (InvalidValueException),
            logger=_LOGGER, interval=600, max_time=7200, jitter=None)
        async def new_data_cb(_):
            """Callback to fetch new data for tomorrows prices at 1300ish CET
            and notify any sensors, about the new data
            """
            # _LOGGER.debug("Called new_data_cb")
            await api.update_tomorrow()
            async_dispatcher_send(hass, EVENT_NEW_PRICE)

        # Handles futures updates
        cb_update_tomorrow = async_track_time_change_in_tz(
            hass,
            new_data_cb,
            hour=13,
            minute=RANDOM_MINUTE,
            second=RANDOM_SECOND,
            tz=await dt_utils.async_get_time_zone("Europe/Stockholm"),
        )

        cb_new_day = async_track_time_change(
            hass, new_day_cb, hour=0, minute=0, second=0
        )

        cb_new_hr = async_track_time_change(hass, new_hr, minute=0, second=0)

        api.listeners.append(cb_update_tomorrow)
        api.listeners.append(cb_new_hr)
        api.listeners.append(cb_new_day)

    return True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up using yaml config file."""
    return await _dry_setup(hass, config)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up nordpool as config entry."""
    res = await _dry_setup(hass, entry.data)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.add_update_listener(async_reload_entry)
    return res


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # This is an issue if you have multiple sensors as everything related to DOMAIN
        # is removed, regardless if you have multiple sensors or not. Doesn't seem to
        # create a big issue for now #TODO
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
