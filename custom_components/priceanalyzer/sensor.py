import logging
import math
from datetime import datetime
from operator import itemgetter
from statistics import mean

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import CONF_REGION
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
import json
from .data import Data
from .const import (
    HOT_WATER_CONFIG,
    HOT_WATER_DEFAULT_CONFIG,
    TEMP_DEFAULT,
    TEMP_FIVE_MOST_EXPENSIVE,
    TEMP_IS_FALLING,
    TEMP_FIVE_CHEAPEST,
    TEMP_TEN_CHEAPEST,
    TEMP_LOW_PRICE,
    TEMP_NOT_CHEAP_NOT_EXPENSIVE,
    TEMP_MINIMUM,
    EVENT_CHECKED_STUFF,
    EVENT_NEW_DATA,
    EVENT_NEW_HOUR,
    API_DATA_LOADED,
    DOMAIN,
    DATA,
    _PRICE_IN
)

# Needed incase a user wants the prices in non local currency
_CURRENCY_TO_LOCAL = {"DKK": "Kr", "NOK": "Kr", "SEK": "Kr", "EUR": "€"}
_CURRENTY_TO_CENTS = {"DKK": "Øre", "NOK": "Øre", "SEK": "Öre", "EUR": "c"}



from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_utils


# Import sensor entity and classes.
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from jinja2 import pass_context

from .misc import extract_attrs, has_junk, is_new, start_of

_LOGGER = logging.getLogger(__name__)

def _dry_setup(hass, config, add_devices, discovery_info=None, unique_id=None):
    region = config.get(CONF_REGION)
    entry_key = unique_id or config.get(CONF_ID) or region
    data = hass.data[DATA].get(entry_key)

    if data is None:
        fallback_key = region
        data = hass.data[DATA].get(fallback_key)
        if data is None:
            raise KeyError(f"Data for entry {entry_key} (region {region}) not found")
    pricecorrection = PriceAnalyzerSensor(data, unique_id)
    vvbsensor = VVBSensor(data, config, unique_id)
    pricesensor = PriceSensor(data, unique_id)
    sensors = [
        pricecorrection,
        vvbsensor,
        pricesensor
    ]
    #data.set_sensors(sensors)
    add_devices(sensors, True)

    #data.check_stuff()


async def async_setup_platform(hass, config, add_devices, discovery_info=None) -> None:
    _dry_setup(hass, config, add_devices, unique_id=config.entry_id)
    return True


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Setup sensor platform for the ui"""
    config = config_entry.data
    region = config.get(CONF_REGION)
    entry_key = config_entry.entry_id or config.get(CONF_ID) or region

    # Ensure the data is available before setting up sensors
    if DATA not in hass.data or entry_key not in hass.data[DATA]:
        # Fallback to region key for backward compatibility
        fallback_key = region if DATA in hass.data else None
        if fallback_key and fallback_key in hass.data[DATA]:
            data = hass.data[DATA][fallback_key]
            hass.data[DATA][entry_key] = data
        else:
            _LOGGER.error("Data not available for entry %s (region %s) during sensor setup", entry_key, region)
        return False
    
    _dry_setup(hass, config, async_add_devices, unique_id=entry_key)
    return True

class VVBSensor(SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    
    # Exclude large attributes from recorder database
    _unrecorded_attributes: frozenset[str] = frozenset({
        "raw_today",
        "raw_tomorrow"
    })

    def __init__(self, data, config, unique_id) -> None:
        self._data = data
        self._hass = self._data.api._hass
        self._config = config
        self._attr_unique_id = unique_id + '_VVBSensor'
        self._unique_id = unique_id + '_VVBSensor'
        self._attr_force_update = True

    def getTemp(self, current_hour, is_tomorrow=False, reason=False):
        temp = self.get_config_key(TEMP_DEFAULT)
        if not isinstance(temp, (int, float)):
            if isinstance(temp, (str)) and (temp == 'on' or temp == 'off'):
                temp = temp
            else:
                temp = 75

        reasonText = 'Default temp'
        if current_hour:
            small_price_difference = self._data.small_price_difference_today is True if is_tomorrow is False else self._data.small_price_difference_tomorrow
            is_low_price = current_hour['is_low_price']
            temp_correction_down = float(current_hour['temperature_correction']) < 0
            is_five_most_expensive = current_hour['is_five_most_expensive'] is True
            is_five_cheapest = current_hour['is_five_cheapest'] is True
            is_ten_cheapest = current_hour['is_ten_cheapest'] is True
            is_min_price = current_hour['is_min'] is True

            max = self._data._max_tomorrow if is_tomorrow else self._data._max
            threshold = self._config.get('price_before_active', "") or 0
            below_threshold = float(threshold) > max

            is_low_compared_to_tomorrow = current_hour['is_low_compared_to_tomorrow']


            is_cheap_compared_to_future = current_hour['is_cheap_compared_to_future']
            #TODO Must tomorrow valid be true before this is true? Was ON from 0000:1300 at 21 feb
            # when price was gaining and gaining, and then false.
            # which is kinda right, and kinda false.
            # right in the case that we keep the water heated until the most expensive periods
            # wrong in the case that we keep it on more than necessary maybe,
            # as it may very well get cheaper overnight.

            # TODO is gaining the next day, set extra temp.
            # TODO if tomorrow is available,
            # and is the cheapest 5 hours for the forseeable future, set temp

            # TODO Setting if price is only going down from now as well. Then set minimum temp?

            if small_price_difference or below_threshold:
                temp = temp
                reasonText = 'Small price difference or below threshold for settings'
            elif is_min_price:
                temp = self.get_config_key(TEMP_MINIMUM)
                reasonText = 'Is minimum price'
            elif is_low_compared_to_tomorrow:
                temp = self.get_config_key(TEMP_FIVE_CHEAPEST)
                reasonText = 'The price is only gaining for today and tomorrow, using config for five cheapest'
            elif is_cheap_compared_to_future:
                temp = self.get_config_key(TEMP_FIVE_CHEAPEST)
                reasonText = 'The price is in the five cheapest hours for the known future, using config for five_cheapest'
            elif is_five_most_expensive:
                temp = self.get_config_key(TEMP_FIVE_MOST_EXPENSIVE)
                reasonText = 'Is five most expensive'
            elif is_five_cheapest:
                temp = self.get_config_key(TEMP_FIVE_CHEAPEST)
                reasonText = 'Is five cheapest'
            elif is_ten_cheapest:
                temp = self.get_config_key(TEMP_TEN_CHEAPEST)
                reasonText = 'Is ten cheapest'
            elif temp_correction_down:
                temp = self.get_config_key(TEMP_IS_FALLING)
                reasonText = 'Is falling'
            elif is_low_price:
                temp = self.get_config_key(TEMP_LOW_PRICE)
                reasonText = 'Is low price'
            else:
                temp = self.get_config_key(TEMP_NOT_CHEAP_NOT_EXPENSIVE)
                reasonText = 'Not cheap, not expensive. '

        if reason:
            return reasonText
        if isinstance(temp, float):
            return temp

        return temp if (reason is False) else reasonText


    def get_config_key(self, key=TEMP_DEFAULT):
        # First check if we have individual config fields (new format)
        individual_key_map = {
            TEMP_DEFAULT: 'temp_default',
            TEMP_FIVE_MOST_EXPENSIVE: 'temp_five_most_expensive',
            TEMP_IS_FALLING: 'temp_is_falling',
            TEMP_FIVE_CHEAPEST: 'temp_five_cheapest',
            TEMP_TEN_CHEAPEST: 'temp_ten_cheapest',
            TEMP_LOW_PRICE: 'temp_low_price',
            TEMP_NOT_CHEAP_NOT_EXPENSIVE: 'temp_not_cheap_not_expensive',
            TEMP_MINIMUM: 'temp_minimum'
        }
        
        # Check if we have the individual field (new format)
        if key in individual_key_map:
            individual_key = individual_key_map[key]
            if individual_key in self._config:
                return self._config[individual_key]
        
        # Fall back to JSON format (old format) for backward compatibility
        config = self._config.get(HOT_WATER_CONFIG, "")
        list = {}
        if config:
            try:
                list = json.loads(config)
            except (json.JSONDecodeError, TypeError):
                list = HOT_WATER_DEFAULT_CONFIG
        else:
            list = HOT_WATER_DEFAULT_CONFIG
            
        if key in list.keys():
            return list[key]
        else:
            return HOT_WATER_DEFAULT_CONFIG[key]



    @property
    def state(self) -> float:
        return self.getTemp(self._data.current_hour)


    def get_today_calculated(self) -> dict:
        today_calculated = []
        today = self._data.today_calculated
        for hour in today:
            item = {
                "start": hour["start"],
                "end": hour["end"],
                "temp": self.getTemp(hour),
                "reason": self.getTemp(hour,False,True)
            }

            today_calculated.append(item)

        return today_calculated

    def get_tomorrow_calculated(self) -> dict:
        tomorrow_calculated = []
        today = self._data.tomorrow_calculated
        for hour in today:
            item = {
                "start": hour["start"],
                "end": hour["end"],
                "temp": self.getTemp(hour, True),
                "reason": self.getTemp(hour,True,True)
            }

            tomorrow_calculated.append(item)
        return tomorrow_calculated

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "reason": self.getTemp(self._data.current_hour,False,True),
            "raw_today": self.get_today_calculated(),
            "raw_tomorrow": self.get_tomorrow_calculated(),
            "unique_id": self.unique_id,
        }


    @property
    def name(self) -> str:
        # Use friendly_name if set, otherwise use region for backward compatibility
        if self._data._attr_name and self._data._attr_name.strip():
            return 'VVBSensor_' + self._data._attr_name
        return 'VVBSensor_' + self._data._area

    @property
    def should_poll(self):
        """Think we need to poll this at the current state of code."""
        return False

    @property
    def icon(self) -> str:
        return "mdi:water-boiler"

    @property
    def unit(self) -> str:
        return '°C'



    @property
    def unit_of_measurement(self) -> str:
        return self.unit


    @property
    def device_info(self):
        return self._data.device_info

    def _update(self, data) -> None:
        self._data.update(data)


    def update_sensor(self):
        self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)
        #self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()
        _LOGGER.debug("called async_added_to_hass %s", self.name)
        async_dispatcher_connect(self._data.api._hass, EVENT_NEW_DATA, self._data.new_day)
        async_dispatcher_connect(self._data.api._hass, EVENT_NEW_HOUR, self._data.new_hr)
        async_dispatcher_connect(self._data.api._hass, API_DATA_LOADED, self._data.check_stuff)
        async_dispatcher_connect(self._data.api._hass, EVENT_CHECKED_STUFF, self.update_sensor)
        await self._data.check_stuff()

class PriceAnalyzerSensor(SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    _unrecorded_attributes: frozenset[str] = frozenset({
        "raw_today",
        "raw_tomorrow", 
        "ten_cheapest_today",
        "five_cheapest_today",
        "ten_cheapest_tomorrow",
        "five_cheapest_tomorrow",
        "current_hour"
    })

    def __init__(
        self,
        data,
        unique_id
    ) -> None:
        self._data = data
        self._hass = self._data.api._hass
        self._attr_unique_id = unique_id + '_priceanalyzer'
        self._unique_id = unique_id + '_priceanalyzer'
        self._attr_force_update = True

    @property
    def name(self) -> str:
        # Use friendly_name if set, otherwise use region for backward compatibility
        if self._data._attr_name and self._data._attr_name.strip():
            return 'Priceanalyzer_' + self._data._attr_name
        return 'Priceanalyzer_' + self._data._area

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def icon(self) -> str:
        return "mdi:sine-wave"

    @property
    def unit(self) -> str:
        return self._data._price_type

    @property
    def unit_of_measurement(self) -> str:
        return '°C'


    @property
    def device_info(self):
        return self._data.device_info


    @property
    def extra_state_attributes(self) -> dict:
        return {
            "display_name": self._data._attr_name,
            "low price": self._data.low_price,
            "tomorrow_valid": self._data.tomorrow_valid,
            'max': self._data._max,
            'min': self._data._min,
            'price_difference_is_small': self._data.small_price_difference_today,
            'price_difference_is_small_tomorrow': self._data.small_price_difference_tomorrow,
            'peak': self._data._peak,
            'off_peak_1': self._data._off_peak_1,
            'off_peak_2': self._data._off_peak_2,
            'average': self._data._average,
            'average_tomorrow': self._data._average_tomorrow,
            "current_hour": self._data.current_hour,
            "raw_today": self._data.today_calculated,
            "raw_tomorrow": self._data.tomorrow_calculated,
            "ten_cheapest_today": self._data._ten_cheapest_today,
            "five_cheapest_today": self._data._five_cheapest_today,
            "ten_cheapest_tomorrow": self._data._ten_cheapest_tomorrow,
            "five_cheapest_tomorrow": self._data._ten_cheapest_tomorrow,
        }


    @property
    def state(self) -> float:
        if self._data.current_hour:
            return self._data.current_hour['temperature_correction']
        else:
            return None

    def _update(self, data) -> None:
        self._data.update(data)

    def update_sensor(self):
        self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)
        #self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()
        _LOGGER.debug("called async_added_to_hass %s", self.name)
        async_dispatcher_connect(self._data.api._hass, EVENT_NEW_DATA, self._data.new_day)
        async_dispatcher_connect(self._data.api._hass, EVENT_NEW_HOUR, self._data.new_hr)
        async_dispatcher_connect(self._data.api._hass, API_DATA_LOADED, self._data.check_stuff)
        async_dispatcher_connect(self._data.api._hass, EVENT_CHECKED_STUFF, self.update_sensor)
        await self._data.check_stuff()


class PriceSensor(SensorEntity):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        data,
        unique_id
    ) -> None:
        self._data = data
        self._hass = self._data.api._hass
        self._attr_unique_id = unique_id + '_priceanalyzer_price'
        self._unique_id = unique_id + '_priceanalyzer_price'
        self._attr_force_update = True

    @property
    def name(self) -> str:
        # Use friendly_name if set, otherwise use region for backward compatibility
        if self._data._attr_name and self._data._attr_name.strip():
            return 'Priceanalyzer_Price_' + self._data._attr_name
        return 'Priceanalyzer_Price_' + self._data._area

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def icon(self) -> str:
        return "mdi:cash"

    @property
    def unit(self) -> str:
        return self._data._price_type

    @property
    def unit_of_measurement(self) -> str:  # FIXME
        """Return the unit of measurement this sensor expresses itself in."""
        _currency = self._data._currency
        if self._data._use_cents is True:
            # Convert unit of measurement to cents based on chosen currency
            _currency = _CURRENTY_TO_CENTS[_currency]
        return "%s/%s" % (_currency, self._data._price_type)


    @property
    def device_info(self):
        return self._data.device_info


    @property
    def extra_state_attributes(self) -> dict:
        return {

        }

    @property
    def state(self) -> float:
        if self._data.current_hour:
            return self._data.current_hour['value']
        else:
            return None

    def _update(self, data) -> None:
        self._data.update(data)

    def update_sensor(self):
        self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()
        _LOGGER.debug("Price Sensors called async_added_to_hass %s", self.name)
        async_dispatcher_connect(self._data.api._hass, EVENT_NEW_DATA, self._data.new_day)
        async_dispatcher_connect(self._data.api._hass, EVENT_NEW_HOUR, self._data.new_hr)
        async_dispatcher_connect(self._data.api._hass, API_DATA_LOADED, self._data.check_stuff)
        async_dispatcher_connect(self._data.api._hass, EVENT_CHECKED_STUFF, self.update_sensor)
        await self._data.check_stuff()
