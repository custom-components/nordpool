import logging
import math
from datetime import datetime
from operator import itemgetter
from statistics import mean

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_REGION
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity, DeviceInfo
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
    API_DATA_LOADED,
    DOMAIN,
    DATA
)


from homeassistant.helpers.template import Template, attach
from homeassistant.util import dt as dt_utils
from jinja2 import pass_context

from .misc import extract_attrs, has_junk, is_new, start_of

_LOGGER = logging.getLogger(__name__)

def _dry_setup(hass, config, add_devices, discovery_info=None, unique_id=None):
    region = config.get(CONF_REGION)
    data = hass.data[DATA][region]
    pricecorrection = PriceAnalyzerSensor(data, unique_id)
    vvbsensor = VVBSensor(data, config, unique_id)
    
    sensors = [
        pricecorrection,
        vvbsensor
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
    _dry_setup(hass, config, async_add_devices, unique_id=config_entry.entry_id)
    return True

class VVBSensor(Entity):
    def __init__(self,data, config, unique_id) -> None:
        self._data = data
        self._hass = self._data.api._hass
        self._config = config
        self._attr_unique_id = unique_id + '_VVBSensor'
        self._unique_id = unique_id + '_VVBSensor'

    def getTemp(self, current_hour, is_tomorrow = False, reason = False):
        temp = self.getConfigKey(TEMP_DEFAULT)
        if not isinstance(temp, (int, float)):
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
            
            is_low_compared_to_tomorrow = False #current_hour['is_low_compared_to_tomorrow']
            #todo is gaining the next day, set extra temp.
            #todo if tomorrow is available, 
            #and is the cheapest 5 hours for the forseeable future, set temp
            #
            if small_price_difference or below_threshold:
                temp = temp
                reasonText = 'Small price difference or below threshold for settings'
            elif is_low_compared_to_tomorrow:
                temp = self.getConfigKey(TEMP_MINIMUM)
                reasonText = 'The price is only gaining for today and tomorrow, using config for minumum price'
            elif is_five_most_expensive:
                temp = self.getConfigKey(TEMP_FIVE_MOST_EXPENSIVE)
                reasonText = 'Is five most expensive'
            elif temp_correction_down:
                temp = self.getConfigKey(TEMP_IS_FALLING)
                reasonText = 'Is falling'
            elif is_min_price:
                temp = self.getConfigKey(TEMP_MINIMUM)
                reasonText = 'Is minimum price'
            elif is_five_cheapest:
                temp = self.getConfigKey(TEMP_FIVE_CHEAPEST)
                reasonText = 'Is five cheapest'
            elif is_ten_cheapest:
                temp = self.getConfigKey(TEMP_TEN_CHEAPEST)
                reasonText = 'Is ten cheapest'
            elif is_low_price:
                temp = self.getConfigKey(TEMP_LOW_PRICE)
                reasonText = 'Is low price'
            else:
                temp = self.getConfigKey(TEMP_NOT_CHEAP_NOT_EXPENSIVE)
                reasonText = 'Not cheap, not expensive. '
                
        if reason:
            return reasonText
        if isinstance(temp, float):
            return temp
        
        return temp if (reason is False) else reasonText


    def getConfigKey(self, key=TEMP_DEFAULT):
        config = self._config.get(HOT_WATER_CONFIG, "")
        list = {}
        if config:
            list = json.loads(config)
        else:
            list = HOT_WATER_DEFAULT_CONFIG
        if(key in list.keys()):
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
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()
        _LOGGER.debug("called async_added_to_hass %s", self.name)
        async_dispatcher_connect(self._data.api._hass, EVENT_NEW_DATA, self._data.check_stuff)
        async_dispatcher_connect(self._data.api._hass, EVENT_CHECKED_STUFF, self.update_sensor)
        await self._data.check_stuff()

class PriceAnalyzerSensor(Entity):
    def __init__(
        self,
        data,
        unique_id
    ) -> None:
        self._data = data
        self._hass = self._data.api._hass
        self._attr_unique_id = unique_id + '_priceanalyzer'
        self._unique_id = unique_id + '_priceanalyzer'

    @property
    def name(self) -> str:
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
            "display_name" : self._data._attr_name,
            "low price": self._data.low_price,
            "tomorrow_valid": self._data.tomorrow_valid,
            "precision": self._data._precision,
            "unique_id": self.unique_id,
            'max': self._data._max,
            'min': self._data._min,
            'price_difference_is_small': self._data.small_price_difference_today,
            'price_difference_is_small_tomorrow': self._data.small_price_difference_tomorrow,
            'peak': self._data._peak,
            'off_peak_1': self._data._off_peak_1,
            'off_peak_2': self._data._off_peak_2,
            'average': self._data._average,
            "current_hour": self._data.current_hour,
            "raw_today": self._data.today_calculated,
            "raw_tomorrow": self._data.tomorrow_calculated,
            "ten_cheapest_today": self._data._ten_cheapest_today,
            "five_cheapest_today": self._data._five_cheapest_today,
            "ten_cheapest_tomorrow": self._data._ten_cheapest_tomorrow,
            "five_cheapest_tomorrow": self._data._ten_cheapest_tomorrow,
            #"five_cheapest_hours_in_future": self._data._cheapest_hours_in_future_sorted[5:]
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
        self.async_write_ha_state()        

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()
        _LOGGER.debug("called async_added_to_hass %s", self.name)
        async_dispatcher_connect(self._data.api._hass, EVENT_NEW_DATA, self._data.check_stuff)
        async_dispatcher_connect(self._data.api._hass, API_DATA_LOADED, self._data.check_stuff)
        async_dispatcher_connect(self._data.api._hass, EVENT_CHECKED_STUFF, self.update_sensor)
        await self._data.check_stuff()
