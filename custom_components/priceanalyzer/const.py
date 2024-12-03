
import logging
import json

from random import randint
from homeassistant.components.sensor import PLATFORM_SCHEMA
import voluptuous as vol
from homeassistant.const import CONF_REGION
import homeassistant.helpers.config_validation as cv


DOMAIN = "priceanalyzer"
DATA = 'priceanalyzer_data'
API_DATA_LOADED = 'priceanalyzer_api_data_loaded'

RANDOM_MINUTE = randint(0, 5)
RANDOM_SECOND = randint(0, 59)

EVENT_NEW_DATA = "priceanalyzer_new_day"
EVENT_NEW_HOUR = "priceanalyzer_new_hour"
EVENT_CHECKED_STUFF = 'pricanalyzer_checked_stuff'
_CURRENCY_LIST = ["DKK", "EUR", "NOK", "SEK"]

PLATFORMS = [
    "sensor",
]

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)


NAME = DOMAIN
VERSION = "1.0"
ISSUEURL = "https://github.com/erlendsellie/priceanalyzer/issues"

STARTUP = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom component
If you have any issues with this you need to open an issue here:
{ISSUEURL}
-------------------------------------------------------------------
"""




_CENT_MULTIPLIER = 100
_PRICE_IN = {"kWh": 1000, "MWh": 0, "Wh": 1000 * 1000}

_REGIONS = {
    "DK1": ["DKK", "Denmark", 0.25],
    "DK2": ["DKK", "Denmark", 0.25],
    "FI": ["EUR", "Finland", 0.255],
    "EE": ["EUR", "Estonia", 0.22],
    "LT": ["EUR", "Lithuania", 0.21],
    "LV": ["EUR", "Latvia", 0.21],
    "NO1": ["NOK", "Norway", 0.25],
    "NO2": ["NOK", "Norway", 0.25],
    "NO3": ["NOK", "Norway", 0.25],
    "NO4": ["NOK", "Norway", 0.25],
    "NO5": ["NOK", "Norway", 0.25],
    "SE1": ["SEK", "Sweden", 0.25],
    "SE2": ["SEK", "Sweden", 0.25],
    "SE3": ["SEK", "Sweden", 0.25],
    "SE4": ["SEK", "Sweden", 0.25],
    # What zone is this?
    "SYS": ["EUR", "System zone", 0.25],
    "FR": ["EUR", "France", 0.055],
    "NL": ["EUR", "Netherlands", 0.21],
    "BE": ["EUR", "Belgium", 0.06],
    "AT": ["EUR", "Austria", 0.20],
    # Unsure about tax rate, correct if wrong
    "GER": ["EUR", "Germany", 0.23],
}


# Needed incase a user wants the prices in non local currency
_CURRENCY_TO_LOCAL = {"DKK": "Kr", "NOK": "Kr", "SEK": "Kr", "EUR": "€"}
_CURRENTY_TO_CENTS = {"DKK": "Øre", "NOK": "Øre", "SEK": "Öre", "EUR": "c"}

DEFAULT_CURRENCY = "NOK"
DEFAULT_REGION = "Kr.sand"
DEFAULT_NAME = "Elspot"


DEFAULT_TEMPLATE = "{{0.01|float}}"


#config for hot water temperature.
TEMP_DEFAULT = 'default_temp'
TEMP_FIVE_MOST_EXPENSIVE = 'five_most_expensive'
TEMP_IS_FALLING = 'is_falling'
TEMP_FIVE_CHEAPEST = 'five_cheapest'
TEMP_TEN_CHEAPEST = 'ten_cheapest'
TEMP_LOW_PRICE = 'low_price'
TEMP_NOT_CHEAP_NOT_EXPENSIVE = 'not_cheap_not_expensive'
TEMP_MINIMUM = 'min_price_for_day'

HOT_WATER_CONFIG = 'hot_water_config'
HOT_WATER_DEFAULT_CONFIG = {
    TEMP_DEFAULT : 75,
    TEMP_FIVE_MOST_EXPENSIVE : 40,
    TEMP_IS_FALLING : 50,
    TEMP_FIVE_CHEAPEST : 70,
    TEMP_TEN_CHEAPEST : 65,
    TEMP_LOW_PRICE : 60,
    TEMP_NOT_CHEAP_NOT_EXPENSIVE : 50,
    TEMP_MINIMUM : 75
}

HOT_WATER_DEFAULT_CONFIG_JSON = json.dumps(HOT_WATER_DEFAULT_CONFIG)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_REGION, default=DEFAULT_REGION): vol.In(
            list(_REGIONS.keys())
        ),
        vol.Optional("friendly_name", default=""): cv.string,
        vol.Optional("currency", default=""): cv.string,
        vol.Optional("VAT", default=True): cv.boolean,
        vol.Optional("low_price_cutoff", default=1.0): cv.small_float,
        vol.Optional("price_type", default="kWh"): vol.In(list(_PRICE_IN.keys())),
        vol.Optional("price_in_cents", default=False): cv.boolean,
        vol.Optional("additional_costs", default=DEFAULT_TEMPLATE): cv.template,
        vol.Optional("multiply_template", default='{{correction * 1}}'): cv.template,
        vol.Optional("hours_to_boost", default=2): int,
        vol.Optional("hours_to_save", default=2): int,
        vol.Optional("pa_price_before_active", default=0.20): float,
        vol.Optional("percent_difference", default=20): int,
        vol.Optional("price_before_active", default=0.20): float,
        vol.Optional(HOT_WATER_CONFIG, default=HOT_WATER_DEFAULT_CONFIG_JSON): cv.string,
    }
)