import logging
from collections import defaultdict
from datetime import datetime, timedelta
from functools import partial
from random import randint

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntry

from homeassistant.core import Config, HomeAssistant

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_REGION, CONF_ID
import homeassistant.helpers.config_validation as cv
from .data import Data


from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.util import dt as dt_utils
from pytz import timezone

from .aio_price import AioPrices
from .events import async_track_time_change_in_tz
from .const import (
    DOMAIN,
    DATA,
    RANDOM_MINUTE,
    RANDOM_SECOND,
    PLATFORM_SCHEMA,
    EVENT_NEW_DATA,
    API_DATA_LOADED,
    _CURRENCY_LIST,
    PLATFORMS,
    CONFIG_SCHEMA,
    NAME,
    VERSION,
    ISSUEURL,
    STARTUP,
    _CENT_MULTIPLIER,
    _REGIONS,
    _CURRENCY_TO_LOCAL,
    _CURRENTY_TO_CENTS,
    DEFAULT_CURRENCY,
    DEFAULT_REGION,
    DEFAULT_NAME,
    DEFAULT_TEMPLATE,
    PLATFORM_SCHEMA
    )   

_LOGGER = logging.getLogger(__name__)

class NordpoolData:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._last_tick = None
        self._data = defaultdict(dict)
        self._tomorrow_valid = False
        self.currency = []
        self.listeners = []

    async def _update(self, type_="today", dt=None):
        _LOGGER.debug("calling _update %s %s", type_, dt)
        hass = self._hass
        client = async_get_clientsession(hass)

        if dt is None:
            dt = dt_utils.now()

        # We dont really need today and morrow
        # when the region is in another timezone
        # as we request data for 3 days anyway.
        # Keeping this for now, but this should be changed.
        for currency in self.currency:
            spot = AioPrices(currency, client)
            data = await spot.hourly(end_date=dt)
            if data:
                self._data[currency][type_] = data["areas"]
                async_dispatcher_send(hass, API_DATA_LOADED)
            else:
                _LOGGER.info("Some crap happend, retrying request later.")
                async_call_later(hass, 20, partial(self._update, type_=type_, dt=dt))

    async def update_today(self, n: datetime):
        _LOGGER.debug("Updating todays prices.")
        await self._update("today")

    async def update_tomorrow(self, n: datetime):
        _LOGGER.debug("Updating tomorrows prices.")
        await self._update(type_="tomorrow", dt=dt_utils.now() + timedelta(hours=24))
        #self._tomorrow_valid = True

    async def _someday(self, area: str, currency: str, day: str):
        """Returns todays or tomorrows prices in a area in the currency"""
        if currency not in _CURRENCY_LIST:
            raise ValueError(
                "%s is a invalid currency possible values are %s"
                % (currency, ", ".join(_CURRENCY_LIST))
            )

        # This is needed as the currency is
        # set in the sensor.
        if currency not in self.currency:
            self.currency.append(currency)
            await self.update_today(None)
            await self.update_tomorrow(None)

        #if(day == 'tomorrow'):
            #self._tomorrow_valid = True

        return self._data.get(currency, {}).get(day, {}).get(area)

    def tomorrow_valid(self) -> bool:
        return self._tomorrow_valid

    async def today(self, area: str, currency: str) -> dict:
        """Returns todays prices in a area in the requested currency"""
        res = await self._someday(area, currency, "today")
        return res

    async def tomorrow(self, area: str, currency: str):
        """Returns tomorrows prices in a area in the requested currency"""
        res = await self._someday(area, currency, "tomorrow")
        if res and len(res) > 0:
            self._tomorrow_valid = True
        return res


async def _dry_setup(hass: HomeAssistant, configEntry: Config) -> bool:
    """Set up using yaml config file."""    
    config = configEntry.data

    if DATA not in hass.data:
        hass.data[DATA] = {}

    if DOMAIN not in hass.data and True: 
        # TODO This is the reason why only one sensor sets up correctly at startup.
        # When the first sensor sets up, the rest does not because domain is in hass.data.
        # If we remove it like this, i think every sensor will use the same api instance?
        #nope, data is called with config from Oslo, for Trondheim.
        api = NordpoolData(hass)
        hass.data[DOMAIN] = api
        

        async def new_day_cb(n):
            """Cb to handle some house keeping when it a new day."""
            _LOGGER.debug("Called new_day_cb callback")
            api._tomorrow_valid = False

            for curr in api.currency:
                if not len(api._data[curr]["tomorrow"]):
                    api._data[curr]["today"] = await api.update_today(None)
                else:
                    api._data[curr]["today"] = api._data[curr]["tomorrow"]
                api._data[curr]["tomorrow"] = {}

            async_dispatcher_send(hass, EVENT_NEW_DATA)

        async def new_hr(n):
            """Callback to tell the sensors to update on a new hour."""
            _LOGGER.debug("Called new_hr callback")
            async_dispatcher_send(hass, EVENT_NEW_DATA)

        async def new_data_cb(n):
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



    pa_config = config
    api = NordpoolData(hass) if hass.data[DOMAIN] is None else hass.data[DOMAIN]
    _LOGGER.debug("Dumping config %r", pa_config)
    _LOGGER.debug("timezone set in ha %r", hass.config.time_zone)
    region = pa_config.get(CONF_REGION)
    friendly_name = pa_config.get("friendly_name", "")
    price_type = pa_config.get("price_type")
    precision = pa_config.get("precision")
    low_price_cutoff = pa_config.get("low_price_cutoff")
    currency = pa_config.get("currency")
    vat = pa_config.get("VAT")
    use_cents = pa_config.get("price_in_cents")
    ad_template = pa_config.get("additional_costs")
    percent_difference = pa_config.get("percent_difference")
    data = Data(
        friendly_name,
        region,
        price_type,
        precision,
        low_price_cutoff,
        currency,
        vat,
        use_cents,
        api,
        ad_template,
        percent_difference,
        hass,
    )
    
    hass.data[DATA][region] = data
    return True


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up using yaml config file."""
    return True
    return await _dry_setup(hass, config)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up nordpool as config entry."""
    res = await _dry_setup(hass, entry)
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    entry.add_update_listener(async_reload_entry)
    return res

# async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry, options):
#     res = await hass.config_entries.async_update_entry(entry,options)
#     self.async_reload_entry(hass,entry)
#     return res


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    if unload_ok:
        for unsub in hass.data[DOMAIN].listeners:
            unsub()
        hass.data.pop(DOMAIN)

        return True

    return False

async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    res = await device_entry.async_unload_entry(hass,config_entry)
    return res


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
