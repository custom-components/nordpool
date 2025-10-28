import logging
from collections import defaultdict
from datetime import datetime, timedelta
from functools import partial
from random import randint

import aiohttp
import backoff
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntry

from homeassistant.core import HomeAssistant
from homeassistant.core_config import Config

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_REGION, CONF_ID
import homeassistant.helpers.config_validation as cv
from .data import Data


from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.util import dt as dt_utils

from pytz import timezone



from .aio_price import AioPrices, InvalidValueException
from .events import async_track_time_change_in_tz
from .const import (
    DOMAIN,
    DATA,
    RANDOM_MINUTE,
    RANDOM_SECOND,
    PLATFORM_SCHEMA,
    EVENT_NEW_DATA,
    EVENT_NEW_HOUR,
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

EVENT_NEW_DAY = "nordpool_update_day"
EVENT_NEW_PRICE = "nordpool_update_new_price"
SENTINEL = object()

_LOGGER = logging.getLogger(__name__)

class NordpoolData:
    def __init__(self, hass: HomeAssistant, time_resolution: str = "1hour") -> None:
        self._hass = hass
        self._last_tick = None
        self._data = defaultdict(dict)
        self._tomorrow_valid = False
        self.currency = []
        self.listeners = []
        self.areas = []
        self.time_resolution = time_resolution  # "15min" or "1hour"

    async def _update(self, type_="today", dt=None, areas=None):
        _LOGGER.debug("calling _update %s %s", type_, dt)
        hass = self._hass
        # Configure client with timeout for better reliability
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        client = async_get_clientsession(hass, timeout=timeout)

        if dt is None:
            dt = dt_utils.now()
        if areas is not None:
            self.areas += [area for area in areas if area not in self.areas]

        # We dont really need today and morrow
        # when the region is in another timezone
        # as we request data for 3 days anyway.
        # Keeping this for now, but this should be changed.
        for currency in self.currency:
            spot = AioPrices(currency, client, time_resolution=self.time_resolution)
            data = await spot.hourly(end_date=dt, areas=self.areas if len(self.areas) > 0 else None)
            if data:
                self._data[currency][type_] = data["areas"]
                async_dispatcher_send(hass, API_DATA_LOADED)
            else:
                _LOGGER.info("Some crap happend, retrying request later.")
                async_call_later(hass, 20, partial(self._update, type_=type_, dt=dt))

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

    def tomorrow_valid(self) -> bool:
        return self._tomorrow_valid

    async def today(self, area: str, currency: str) -> dict:
        """Returns todays prices in a area in the requested currency"""
        res = await self._someday(area, currency, "today")
        return res

    async def tomorrow(self, area: str, currency: str):
        """Returns tomorrows prices in a area in the requested currency"""

        dt = dt_utils.now()
        if(dt.hour < 11):
            return []

        # TODO Handle when API returns todays prices for tomorrow.
        res = await self._someday(area, currency, "tomorrow")
        if res and len(res) > 0 and len(res['values']) > 0:
            starttime = res['values'][0].get('start', None)
            if starttime:
                start = dt_utils.as_local(starttime)
                _LOGGER.debug("Fetching tomorrow. Start: %s", starttime)
                self._tomorrow_valid = True
                _LOGGER.debug("Setting Tomrrow Valid to True. Res: %s", res)
                return res
                # TODO fix this logic.
                # if start > dt:
                #     _LOGGER.debug('The input date is in the future')
                #     self._tomorrow_valid = True
                #     _LOGGER.debug("Setting Tomrrow Valid to True. Res: %s", res)
                #     return res
                # else:
                #     _LOGGER.debug('The input date is in the past')
                #     return []
        return []


async def _dry_setup(hass: HomeAssistant, configEntry: Config) -> bool:
    """Set up using yaml config file."""
    config = configEntry.data

    if DATA not in hass.data:
        hass.data[DATA] = {}

    if DOMAIN not in hass.data:
        # Initialize the API only once
        time_resolution = config.get("time_resolution", "hourly")
        api = NordpoolData(hass, time_resolution=time_resolution)
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
            tz=timezone("Europe/Stockholm"),
        )

        cb_new_day = async_track_time_change(
            hass, new_day_cb, hour=0, minute=0, second=0
        )

        # Update interval depends on time resolution
        # For quarterly resolution: update every 15 minutes
        # For hourly resolution: update every hour
        if time_resolution == "quarterly":
            cb_new_hr = async_track_time_change(
                hass, new_hr, minute=[0, 15, 30, 45], second=0
            )
        else:  # hourly
            cb_new_hr = async_track_time_change(
                hass, new_hr, minute=0, second=0
            )

        api.listeners.append(cb_update_tomorrow)
        api.listeners.append(cb_new_hr)
        api.listeners.append(cb_new_day)

    pa_config = config
    api = hass.data[DOMAIN]  # Use the existing API instance
    region = pa_config.get(CONF_REGION)
    friendly_name = pa_config.get("friendly_name", "")
    price_type = pa_config.get("price_type")

    low_price_cutoff = pa_config.get("low_price_cutoff")
    currency = pa_config.get("currency")
    vat = pa_config.get("VAT")
    use_cents = pa_config.get("price_in_cents")
    ad_template = pa_config.get("additional_costs")
    multiply_template = pa_config.get("multiply_template")
    num_hours_to_boost = pa_config.get("hours_to_boost")
    num_hours_to_save = pa_config.get("hours_to_save")
    percent_difference = pa_config.get("percent_difference")
    data = Data(
        friendly_name,
        region,
        price_type,
        low_price_cutoff,
        currency,
        vat,
        use_cents,
        api,
        ad_template,
        multiply_template,
        num_hours_to_boost,
        num_hours_to_save,
        percent_difference,
        hass,
        pa_config
    )

    # Check if this region is already set up to prevent duplicates
    if region in hass.data[DATA]:
        _LOGGER.warning("Region %s already set up, skipping duplicate setup", region)
        return True
    
    hass.data[DATA][region] = data
    return True


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up using yaml config file."""
    return True
    return await _dry_setup(hass, config)

async def async_migrate_entry(title, domain) -> bool:
    #sorry, we dont support migrate
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up nordpool as config entry."""
    try:
        # Set up the data layer first
        await _dry_setup(hass, entry)
        
        # Set up the platforms (sensors)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        # Add update listener
        entry.add_update_listener(async_reload_entry)
        
        # Return True only after everything is set up
        return True
    except Exception as e:
        _LOGGER.error("Failed to set up priceanalyzer: %s", e)
        return False

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
