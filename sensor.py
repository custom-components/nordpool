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
    TEMP_MINIMUM
)


from homeassistant.helpers.template import Template, attach
from homeassistant.util import dt as dt_utils
from jinja2 import pass_context

#from .device import Device

from . import DOMAIN, EVENT_NEW_DATA, DATA
from .misc import extract_attrs, has_junk, is_new, start_of

_LOGGER = logging.getLogger(__name__)

# _CENT_MULTIPLIER = 100
# _PRICE_IN = {"kWh": 1000, "MWh": 0, "Wh": 1000 * 1000}
# _REGIONS = {
#     "DK1": ["DKK", "Denmark", 0.25],
#     "DK2": ["DKK", "Denmark", 0.25],
#     "FI": ["EUR", "Finland", 0.24],
#     "EE": ["EUR", "Estonia", 0.20],
#     "LT": ["EUR", "Lithuania", 0.21],
#     "LV": ["EUR", "Latvia", 0.21],
#     "Oslo": ["NOK", "Norway", 0.25],
#     "Kr.sand": ["NOK", "Norway", 0.25],
#     "Bergen": ["NOK", "Norway", 0.25],
#     "Molde": ["NOK", "Norway", 0.25],
#     "Tr.heim": ["NOK", "Norway", 0.25],
#     "Tromsø": ["NOK", "Norway", 0.25],
#     "SE1": ["SEK", "Sweden", 0.25],
#     "SE2": ["SEK", "Sweden", 0.25],
#     "SE3": ["SEK", "Sweden", 0.25],
#     "SE4": ["SEK", "Sweden", 0.25],
#     # What zone is this?
#     "SYS": ["EUR", "System zone", 0.25],
#     "FR": ["EUR", "France", 0.055],
#     "NL": ["EUR", "Netherlands", 0.21],
#     "BE": ["EUR", "Belgium", 0.21],
#     "AT": ["EUR", "Austria", 0.20],
#     # Tax is disabled for now, i need to split the areas
#     # to handle the tax.
#     "DE-LU": ["EUR", "Germany and Luxembourg", 0],
# }

# # Needed incase a user wants the prices in non local currency
# _CURRENCY_TO_LOCAL = {"DKK": "Kr", "NOK": "Kr", "SEK": "Kr", "EUR": "€"}
# _CURRENTY_TO_CENTS = {"DKK": "Øre", "NOK": "Øre", "SEK": "Öre", "EUR": "c"}

# DEFAULT_CURRENCY = "NOK"
# DEFAULT_REGION = "Kr.sand"
# DEFAULT_NAME = "Elspot"


# DEFAULT_TEMPLATE = "{{0.0|float}}"


# PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
#     {
#         vol.Optional(CONF_REGION, default=DEFAULT_REGION): vol.In(
#             list(_REGIONS.keys())
#         ),
#         vol.Optional("friendly_name", default=""): cv.string,
#         # This is only needed if you want the some area but want the prices in a non local currency
#         vol.Optional("currency", default=""): cv.string,
#         vol.Optional("VAT", default=True): cv.boolean,
#         vol.Optional("precision", default=3): cv.positive_int,
#         vol.Optional("low_price_cutoff", default=1.0): cv.small_float,
#         vol.Optional("price_type", default="kWh"): vol.In(list(_PRICE_IN.keys())),
#         vol.Optional("price_in_cents", default=False): cv.boolean,
#         vol.Optional("additional_costs", default=DEFAULT_TEMPLATE): cv.template,
#     }
# )


def _dry_setup(hass, config, add_devices, discovery_info=None):
    """Setup the damn platform using yaml."""
    # _LOGGER.debug("Dumping config %r", config)
    # _LOGGER.debug("timezone set in ha %r", hass.config.time_zone)
    # region = config.get(CONF_REGION)
    # friendly_name = config.get("friendly_name", "")
    # price_type = config.get("price_type")
    # precision = config.get("precision")
    # low_price_cutoff = config.get("low_price_cutoff")
    # currency = config.get("currency")
    # vat = config.get("VAT")
    # use_cents = config.get("price_in_cents")
    # ad_template = config.get("additional_costs")
    # percent_difference = config.get("percent_difference")
    # api = hass.data[DOMAIN]
    # data = Data(
    #     friendly_name,
    #     region,
    #     price_type,
    #     precision,
    #     low_price_cutoff,
    #     currency,
    #     vat,
    #     use_cents,
    #     api,
    #     ad_template,
    #     percent_difference,
    #     hass
    # )
    
    region = config.get(CONF_REGION)
    data = hass.data[DATA][region]
    pricecorrection = PriceAnalyzerSensor(data)
    vvbsensor = VVBSensor(data, config)
    
    sensors = [
        pricecorrection,
        vvbsensor
    ]
    
    add_devices(sensors, True)
    data.set_sensors(sensors)
    data.check_stuff()


async def async_setup_platform(hass, config, add_devices, discovery_info=None) -> None:
    _dry_setup(hass, config, add_devices)
    return True


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Setup sensor platform for the ui"""
    config = config_entry.data
    _dry_setup(hass, config, async_add_devices)
    return True

class VVBSensor(Entity):
    def __init__(self,data, config) -> None:
        self._data = data
        self._hass = self._data.api._hass
        self._config = config

    def getTemp(self, current_hour, is_tomorrow = False, reason = False) -> float:
        
        
        
        temp = self.getConfigKey(TEMP_DEFAULT) or 75
        reasonText = 'Default temp'
        current_hour
        if current_hour:
            small_price_difference = self._data.small_price_difference_today is True if is_tomorrow is False else self._data.small_price_difference_tomorrow
            is_low_price = current_hour['is_low_price']
            temp_correction_down = float(current_hour['temperature_correction']) < 0
            is_five_most_expensive = current_hour['is_five_most_expensive'] is True
            is_five_cheapest = current_hour['is_five_cheapest'] is True
            is_ten_cheapest = current_hour['is_ten_cheapest'] is True
            is_min_price = current_hour['is_min'] is True
            
            
            if small_price_difference:
                temp = temp
                reasonText = 'Small price difference'
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
        # hour = current_hour['start'] if current_hour else None 
        # _LOGGER.debug("called getTemp for  %s with temp %s for hour %s", self.name, temp, hour)
        return temp if (reason is False) else reasonText


    def getConfigKey(self, key=TEMP_DEFAULT):
        
        config = self._config.get(HOT_WATER_CONFIG, "")
    
        list = {}
        if config:
            list = json.loads(config)
    
        else:
            list = HOT_WATER_DEFAULT_CONFIG
    
            
        #todo support incomplete userconfig.
        _LOGGER.debug("Config for VVB for %s: %s", self.name, list)
        
        if(key in list.keys()):
            return list[key]
        else:
            return HOT_WATER_DEFAULT_CONFIG[key]
    

    
    @property
    def state(self) -> float:
        return self.getTemp(self._data.current_hour) # todo, binary sensor can use this and cast to bool temp > 50
    
    
    def get_today_calculated(self) -> dict:
        today_calculated = []
        today = self._data.today_calculated
        for hour in today:
            item = {
                "start": hour["start"],
                "end": hour["end"],
                "temp": self.getTemp(hour),
                "reason": self.getTemp(hour,False,True),
                "binary": float(self.getTemp(hour,False)) > 50,
            }
            
            today_calculated.append(item)

        #_LOGGER.debug("called today_calculated for  %s. today: %s today_calculated: %s", self.name, today, today_calculated)
        return today_calculated
        
    def get_tomorrow_calculated(self) -> dict:
        tomorrow_calculated = []
        today = self._data.tomorrow_calculated
        for hour in today:
            item = {
                "start": hour["start"],
                "end": hour["end"],
                "temp": self.getTemp(hour, True),
                "reason": self.getTemp(hour,True,True),
                "binary": float(self.getTemp(hour,True)) > 50,
                
            }
            
            tomorrow_calculated.append(item)
        return tomorrow_calculated
                
    @property
    def extra_state_attributes(self) -> dict:
        return {
            "reason": self.getTemp(self._data.current_hour,False,True),
            "raw_today": self.get_today_calculated(),
            "raw_tomorrow": self.get_tomorrow_calculated(),
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
        return "mdi:sine-wave"

    @property
    def unit(self) -> str:
        return '°C'


    @property
    def unit_of_measurement(self) -> str:
        return '°C'

    @property
    def unique_id(self):
        name = "priceanalyzerVVB_%s_%s_%s_%s_%s_%s" % (
            self._data._price_type,
            self._data._area,
            self._data._currency,
            self._data._precision,
            self._data._low_price_cutoff,
            self._data._vat,
        )
        name = name.lower().replace(".", "")
        return name

    @property
    def device_info(self):
        return self._data.device_info
        return DeviceInfo(
            identifiers={(DOMAIN, self._data.device_unique_id)},
            name=self._data.device_name,
            manufacturer=DOMAIN,
        )

        return DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            name=self.name,
            manufacturer=DOMAIN,
        )
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": DOMAIN,
        }


    def _update(self, data) -> None:
        _LOGGER.debug("called update() for %s with %s", self.name, data)
        self._data.update(data)

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()
        _LOGGER.debug("called async_added_to_hass %s", self.name)
        async_dispatcher_connect(self._data.api._hass, EVENT_NEW_DATA, self._data.check_stuff)
        await self._data.check_stuff()

class PriceAnalyzerSensor(Entity):
    def __init__(
        self,
        data,
    ) -> None:
        self._data = data
        self._hass = self._data.api._hass

    @property
    def name(self) -> str:
        return 'Priceanalyzer_' + self._data._area

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        #return True # Need to poll until we fix callback to data class for state-write. 
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
    def unique_id(self):
        name = "priceanalyzer_%s_%s_%s_%s_%s_%s" % (
            self._data._price_type,
            self._data._area,
            self._data._currency,
            self._data._precision,
            self._data._low_price_cutoff,
            self._data._vat,
        )
        name = name.lower().replace(".", "")
        return name

    @property
    def device_info(self):
        return self._data.device_info
        return DeviceInfo(
            identifiers={(DOMAIN, self._data.device_unique_id)},
            name=self._data.device_name,
            manufacturer=DOMAIN,
        )

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "display_name" : self._data._attr_name,
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
        _LOGGER.debug("called update() for %s with %s", self.name, data)
        self._data.update(data)

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()
        _LOGGER.debug("called async_added_to_hass %s", self.name)
        async_dispatcher_connect(self._data.api._hass, EVENT_NEW_DATA, self._data.check_stuff)
        await self._data.check_stuff()

