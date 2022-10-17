
import logging
import json

from random import randint
from homeassistant.components.sensor import PLATFORM_SCHEMA
import voluptuous as vol
from homeassistant.const import CONF_REGION
import homeassistant.helpers.config_validation as cv


DOMAIN = "priceanalyzer"
DATA = 'priceanalyzer_data'

RANDOM_MINUTE = randint(10, 30)
RANDOM_SECOND = randint(0, 59)

EVENT_NEW_DATA = "priceanalyzer_update"
_CURRENCY_LIST = ["DKK", "EUR", "NOK", "SEK"]

PLATFORMS = [
    "sensor",
]

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)


NAME = DOMAIN
VERSION = "0.0.30"
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

# Needed incase a user wants the prices in non local currency
_CURRENCY_TO_LOCAL = {"DKK": "Kr", "NOK": "Kr", "SEK": "Kr", "EUR": "€"}
_CURRENTY_TO_CENTS = {"DKK": "Øre", "NOK": "Øre", "SEK": "Öre", "EUR": "c"}

DEFAULT_CURRENCY = "NOK"
DEFAULT_REGION = "Kr.sand"
DEFAULT_NAME = "Elspot"


DEFAULT_TEMPLATE = "{{0.0|float}}"


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
        # This is only needed if you want the some area but want the prices in a non local currency
        vol.Optional("currency", default=""): cv.string,
        vol.Optional("VAT", default=True): cv.boolean,
        vol.Optional("precision", default=3): cv.positive_int,
        vol.Optional("low_price_cutoff", default=1.0): cv.small_float,
        vol.Optional("price_type", default="kWh"): vol.In(list(_PRICE_IN.keys())),
        vol.Optional("price_in_cents", default=False): cv.boolean,
        vol.Optional("additional_costs", default=DEFAULT_TEMPLATE): cv.template,
        vol.Optional(HOT_WATER_CONFIG, default=HOT_WATER_DEFAULT_CONFIG_JSON): cv.string,
    }
)