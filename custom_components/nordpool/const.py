import voluptuous as vol
from random import randint

DOMAIN = "nordpool"
RANDOM_MINUTE = randint(10, 30)
RANDOM_SECOND = randint(0, 59)
EVENT_NEW_HOUR = "nordpool_update_hour"
EVENT_NEW_DAY = "nordpool_update_day"
EVENT_NEW_PRICE = "nordpool_update_new_price"
SENTINEL = object()

_CURRENCY_LIST = ["DKK", "EUR", "NOK", "SEK"]


CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)

NAME = DOMAIN
VERSION = "0.0.17"
ISSUEURL = "https://github.com/custom-components/nordpool/issues"


tzs = {
    "DK1": "Europe/Copenhagen",
    "DK2": "Europe/Copenhagen",
    "FI": "Europe/Helsinki",
    "EE": "Europe/Tallinn",
    "LT": "Europe/Vilnius",
    "LV": "Europe/Riga",
    "NO1": "Europe/Oslo",
    "NO2": "Europe/Oslo",
    "NO3": "Europe/Oslo",
    "NO4": "Europe/Oslo",
    "NO5": "Europe/Oslo",
    "SE1": "Europe/Stockholm",
    "SE2": "Europe/Stockholm",
    "SE3": "Europe/Stockholm",
    "SE4": "Europe/Stockholm",
    # What zone is this?
    "SYS": "Europe/Stockholm",
    "FR": "Europe/Paris",
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "AT": "Europe/Vienna",
    "GER": "Europe/Berlin",
}

# List of page index for hourly data
# Some are disabled as they don't contain the other currencies, NOK etc,
# or there are some issues with data parsing for some ones' DataStartdate.
# Lets come back and fix that later, just need to adjust the self._parser.
# DataEnddate: "2021-02-11T00:00:00"
# DataStartdate: "0001-01-01T00:00:00"
COUNTRY_BASE_PAGE = {
    # "SYS": 17,
    "NO": 23,
    "SE": 29,
    "DK": 41,
    # "FI": 35,
    # "EE": 47,
    # "LT": 53,
    # "LV": 59,
    # "AT": 298578,
    # "BE": 298736,
    # "DE-LU": 299565,
    # "FR": 299568,
    # "NL": 299571,
    # "PL": 391921,
}

AREA_TO_COUNTRY = {
    "SYS": "SYS",
    "SE1": "SE",
    "SE2": "SE",
    "SE3": "SE",
    "SE4": "SE",
    "FI": "FI",
    "DK1": "DK",
    "DK2": "DK",
    "OSLO": "NO",
    "KR.SAND": "NO",
    "BERGEN": "NO",
    "MOLDE": "NO",
    "TR.HEIM": "NO",
    "TROMSØ": "NO",
    "EE": "EE",
    "LV": "LV",
    "LT": "LT",
    "AT": "AT",
    "BE": "BE",
    "DE-LU": "DE-LU",
    "FR": "FR",
    "NL": "NL",
    "PL ": "PL",
}

INVALID_VALUES = frozenset((None, float("inf")))

DEFAULT_TEMPLATE = "{{0.0|float}}"


_CENT_MULTIPLIER = 100
_PRICE_IN = {"kWh": 1000, "MWh": 1, "Wh": 1000 * 1000}
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
DEFAULT_REGION = list(_REGIONS.keys())[0]
DEFAULT_NAME = "Elspot"
