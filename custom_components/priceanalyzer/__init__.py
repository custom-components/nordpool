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
        _LOGGER.debug("calling _update %s %s for areas %s", type_, dt, areas)
        start_time = dt_utils.now()
        hass = self._hass
        # Get the default client session
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
            spot = AioPrices(currency, client, time_resolution=self.time_resolution)
            data = await spot.hourly(end_date=dt, areas=self.areas if len(self.areas) > 0 else None)
            if data:
                self._data[currency][type_] = data["areas"]
                elapsed = (dt_utils.now() - start_time).total_seconds()
                _LOGGER.debug("Successfully fetched %s data for currency %s in %s seconds", 
                            type_, currency, elapsed)
                async_dispatcher_send(hass, API_DATA_LOADED)
            else:
                elapsed = (dt_utils.now() - start_time).total_seconds()
                _LOGGER.warning("Data fetch failed for %s after %s seconds, retrying in 20 seconds. Currency: %s, Areas: %s", 
                              type_, elapsed, currency, self.areas)
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

    # Ensure DATA dictionary exists
    if DATA not in hass.data:
        hass.data[DATA] = {}
        _LOGGER.debug("Initialized DATA dictionary")

    if DOMAIN not in hass.data:
        # Initialize the API only once
        time_resolution = config.get("time_resolution", "hourly")
        api = NordpoolData(hass, time_resolution=time_resolution)
        hass.data[DOMAIN] = api
        _LOGGER.debug("Initialized API with time_resolution: %s", time_resolution)


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
            logger=_LOGGER, interval=600, max_time=7200, jitter=None,
            on_backoff=lambda details: _LOGGER.warning(
                "Tomorrow data fetch failed, retrying in %s seconds (attempt %s): %s",
                details['wait'], details['tries'], details['exception']
            ),
            on_giveup=lambda details: _LOGGER.error(
                "Tomorrow data fetch failed permanently after %s attempts over %s seconds: %s",
                details['tries'], details.get('elapsed', 'unknown'), details['exception']
            ))
        async def new_data_cb(_):
            """Callback to fetch new data for tomorrows prices at 1300ish CET
            and notify any sensors, about the new data
            """
            _LOGGER.debug("Called new_data_cb - fetching tomorrow's data")
            await api.update_tomorrow()
            async_dispatcher_send(hass, EVENT_NEW_PRICE)
            _LOGGER.debug("Successfully fetched tomorrow's data and sent update event")

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
    price_type = pa_config.get("price_type", "kWh")  # Default to kWh if not specified

    low_price_cutoff = pa_config.get("low_price_cutoff", 1.0)
    currency = pa_config.get("currency", "")
    vat = pa_config.get("VAT", True)
    use_cents = pa_config.get("price_in_cents", False)
    ad_template = pa_config.get("additional_costs", "{{0.01|float}}")
    multiply_template = pa_config.get("multiply_template", "{{correction * 1}}")
    num_hours_to_boost = pa_config.get("hours_to_boost", 2)
    num_hours_to_save = pa_config.get("hours_to_save", 2)
    percent_difference = pa_config.get("percent_difference", 20)
    
    # Get entry_id first so we can pass it to Data constructor
    entry_id = getattr(configEntry, "entry_id", None) or pa_config.get(CONF_ID)
    if entry_id is None:
        entry_id = f"{region}_{len(hass.data[DATA])}"
    
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
        pa_config,
        entry_id
    )

    if entry_id in hass.data[DATA]:
        _LOGGER.debug("Replacing existing data for entry %s (region %s)", entry_id, region)

    try:
        hass.data[DATA][entry_id] = data
        _LOGGER.debug("Successfully set up entry %s for region %s", entry_id, region)
        return True
    except Exception as e:
        _LOGGER.error("Failed to set up entry %s for region %s: %s", entry_id, region, e)
        return False


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
        setup_ok = await _dry_setup(hass, entry)
        if not setup_ok:
            _LOGGER.error("Failed to set up data layer for priceanalyzer")
            return False
        
        # Set up the platforms (sensors) - ensure this completes before returning
        # Support both old (2024.x) and new (2025.11+) HA versions
        if hasattr(hass.config_entries, 'async_forward_entry_setups'):
            # HA 2025.11+ - use plural version
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        else:
            # HA 2024.x and older - use singular version
            for platform in PLATFORMS:
                await hass.config_entries.async_forward_entry_setup(entry, platform)
        
        # Add update listener only after successful setup
        entry.add_update_listener(async_reload_entry)
        
        _LOGGER.debug("Successfully set up priceanalyzer entry: %s", entry.entry_id)
        return True
    except Exception as e:
        _LOGGER.error("Failed to set up priceanalyzer: %s", e)
        # Clean up on failure using entry_id
        if DATA in hass.data and entry.entry_id in hass.data[DATA]:
            hass.data[DATA].pop(entry.entry_id, None)
            _LOGGER.debug("Cleaned up failed setup for entry %s", entry.entry_id)
        return False

# async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry, options):
#     res = await hass.config_entries.async_update_entry(entry,options)
#     self.async_reload_entry(hass,entry)
#     return res


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload all platforms - support both old and new HA versions
    if hasattr(hass.config_entries, 'async_forward_entry_unloads'):
        # HA 2025.11+ - use plural version
        unload_ok = await hass.config_entries.async_forward_entry_unloads(entry, PLATFORMS)
    else:
        # HA 2024.x and older - use singular version
        unload_results = []
        for platform in PLATFORMS:
            result = await hass.config_entries.async_forward_entry_unload(entry, platform)
            unload_results.append(result)
        unload_ok = all(unload_results)

    if unload_ok:
        # Clean up the entry-specific data using entry_id (not region)
        # This allows multiple setups with the same region
        entry_id = entry.entry_id
        if DATA in hass.data and entry_id in hass.data[DATA]:
            hass.data[DATA].pop(entry_id)
            _LOGGER.debug("Cleaned up data for entry %s (region: %s)", entry_id, entry.data.get(CONF_REGION))
        
        # Clean up the API data if no more entries are configured
        if DATA in hass.data and len(hass.data[DATA]) == 0:
            if DOMAIN in hass.data:
                for unsub in hass.data[DOMAIN].listeners:
                    unsub()
                hass.data.pop(DOMAIN)
                _LOGGER.debug("Cleaned up API data as no entries remain")

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
