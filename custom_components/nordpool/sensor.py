import logging
import datetime as dt
import math

import pprint


from operator import itemgetter

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ATTRIBUTION, CONF_CURRENCY, CONF_REGION, CONF_NAME

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from homeassistant.helpers.entity import Entity


_LOGGER = logging.getLogger(__name__)

_CURRENCY_LIST = ["DKK", "EUR", "NOK", "SEK"]

_CURRENCY_FRACTION = {"DKK": "Øre", "EUR": "Cent", "NOK": "Øre", "SEK": "Öre"}

_PRICE_IN = {"kWh": 1000, "mWh": 0}

_REGION_NAME = [
    "DK1",
    "DK2",
    "EE",
    "FI",
    "LT",
    "LV",
    "Oslo",
    "Kr.sand",
    "Bergen",
    "Molde",
    "Tr.heim",
    "Tromsø",
    "SE1",
    "SE2",
    "SE3",
    "SE4",
    "SYS",
]

DEFAULT_CURRENCY = "NOK"
DEFAULT_REGION = "Kr.sand"
DEFAULT_NAME = "Elspot kWh"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_CURRENCY, default=DEFAULT_CURRENCY): vol.In(_CURRENCY_LIST),
        vol.Optional(CONF_REGION, default=DEFAULT_REGION): vol.In(_REGION_NAME),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional("VAT", default=0.0): cv.small_float,
        vol.Optional("price_type", default="kWh"): vol.In(list(_PRICE_IN.keys())),
    }
)


def setup_platform(hass, config, add_devices, discovery_info=None):
    _LOGGER.info("%r" % config)
    currency = config.get(CONF_CURRENCY)
    region = config.get(CONF_REGION)
    name = config.get(CONF_NAME)
    vat = config.get("VAT")
    price_type = config.get("price_type")
    # Add support for muliple sensors.
    sensor = NordpoolSensor(name, currency, region, vat, price_type)

    add_devices([sensor])
    hass.data[name] = sensor


class NordpoolSensor(Entity):
    def __init__(self, name, currency, region, vat, price_type) -> None:
        self._name = name
        self._currency = currency
        self._area = region
        self._vat = vat
        self._price_type = price_type

        # Price by current hour.
        self._current_price = 0

        # Holds the data for today and morrow.
        self._data_today = None
        self._data_tomorrow = None

        # Values for the day.
        self._average = None
        self._max = None
        self._min = None
        self._off_peak_1 = None
        self._off_peak_2 = None
        self._peak = None

        self._last_update = None
        self._next_update = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def icon(self) -> str:
        return "mdi:flash"

    @property
    def unit(self) -> str:
        return self._currency

    @property
    def state(self) -> float:
        return self.current_price

    @property
    def low_price(self):
        """Check if the price is lower then avg"""
        return self.current_price > self._average

    def _calc_price(self, value=None):
        """Calculate price based on the users settings."""
        if value is None:
            value = self._current_price

        if math.isinf(value):
            _LOGGER.info("api returned junk infitiy")
            # So far this seems to happend on peek, offpeek1 and offpeak2
            # if this happens often we could calculate this prices ourself.
            # Peak = 08:00 to 20:00
            # Off peak 1 = 00:00 to 08:00
            # Off peak 2 = 20:00 to 00:00
            return 0.0

        # The api returns prices in mwh
        return value / _PRICE_IN[self._price_type] * (float(1 + self._vat))

    def _update(self, data):
        _LOGGER.info("Called update")
        self._average = self._calc_price(data.get("Average"))
        self._min = self._calc_price(data.get("Min"))
        self._max = self._calc_price(data.get("Max"))
        self._off_peak_1 = self._calc_price(data.get("Off-peak 1"))
        self._off_peak_2 = self._calc_price(data.get("Off-peak 2"))
        self._peak = self._calc_price(data.get("Peak"))
        self._last_update = dt_util.now()
        self._next_update = self._last_update + dt.timedelta(days=1)
        # Seem to release new prices at 1400.
        self._next_update.replace(hour=14, minute=0, second=0, microsecond=0)

    @property
    def current_price(self):
        return self._calc_price()

    def _someday(self, data):
        todays = []
        for item in data.get("values", []):
            item["value"] = self._calc_price(item["value"])
            todays.append(item)

        return [i["value"] for i in sorted(todays, key=itemgetter("start"))]

    @property
    def today(self):
        """Get todays prices"""
        return self._someday(self._data_today)

    @property
    def tomorrow(self):
        """Get todays prices"""
        return self._someday(self._data_tomorrow)

    @property
    def device_state_attributes(self) -> dict:
        return {
            "current_price": self.current_price,
            "average": self._average,
            "off peak 1": self._off_peak_1,
            "off peak 2": self._off_peak_2,
            "peak": self._peak,
            "min": self._min,
            "max": self._max,
        }

    def _update_current_price(self) -> None:
        now = dt_util.utcnow()
        if now.hour > self._last_update.hour or self._current_price in (0, None, 0.0):
            if self._data_today:
                for value in self._data_today.get("values", []):
                    if now.hour == value.get("start").hour:
                        _LOGGER.info("Update current price")
                        self._current_price = value.get("value")
            else:
                _LOGGER.info("no data :'(")

    def update(self) -> None:
        """Update the attributes"""
        from nordpool import elspot

        # Add todays data :)
        if self._data_today is None:
            local_now = dt_util.as_local(dt_util.utcnow())
            spot = elspot.Prices(self._currency)
            data = spot.hourly(end_date=local_now, areas=[self._area])
            # _LOGGER.info('%r', pprint.pprint(data, indent=4))

            if data:
                area = list(data["areas"].values())[0]
                self._data_today = area
                self._update(area)

        if self._data_tomorrow is None:
            spot = elspot.Prices(self._currency)
            data = spot.hourly(areas=[self._area])
            if data:
                area = list(data["areas"].values())[0]
                # lets check that the data is valid, the api adds infinty for missing values.
                if not math.isinf(area["Average"]):
                    self._data_tomorrow = area
                else:
                    _LOGGER.info("Api returned a infinty value, full was %r", area)

        now = dt_util.now()
        if self._next_update is not None and now >= self._next_update:
            _LOGGER.info("Updated because of tick.")
            spot = elspot.Prices(self._currency)
            data = spot.hourly(areas=[self._area])
            if data:
                area = list(data["areas"].values())[0]
                if not math.isinf(area["Average"]):
                    self._data_tomorrow = area
                    self._update(area)
                else:
                    _LOGGER.info("Api returned a infinty value, full was %r", area)

        if now.date() > self._last_update.date():
            _LOGGER.info("There is a new day. replacing todays data with tomorrow")
            self._data_today = self._data_tomorrow
            self._update(area)

        self._update_current_price()
