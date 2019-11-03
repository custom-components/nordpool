import logging
import math
from operator import itemgetter

import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_REGION
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
import pendulum

from . import DOMAIN
from .misc import is_new, has_junk, extract_attrs


_LOGGER = logging.getLogger(__name__)


_PRICE_IN = {"kWh": 1000, "MWh": 0, "W": 1000 * 1000}
_REGIONS = {
    "DK1": ["DKK", "Denmark", 0.25],
    "DK2": ["DKK", "Denmark", 0.25],
    "FI": ["EUR", "Finland", 0.24],
    "EE": ["EUR", "Estonia", 0.20],
    "LT": ["EUR", "Lithuania", 0.21],
    "LV": ["EUR", "Latvia", 0.21],
    "Oslo": ["NOK", "Norway", 0, 25],
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
}

# Needed incase a user wants the prices in non local currency
_CURRENCY_TO_LOCAL = {"DKK": "Kr", "NOK": "Kr", "SEK": "Kr", "EUR": "€"}

DEFAULT_CURRENCY = "NOK"
DEFAULT_REGION = "Kr.sand"
DEFAULT_NAME = "Elspot"


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_REGION, default=DEFAULT_REGION): vol.In(
            list(_REGIONS.keys())
        ),
        vol.Optional("friendly_name", default=""): cv.string,
        # This is only needed if you want the some area but want the prices in a non local currency
        vol.Optional("currency", default=""): cv.string,
        vol.Optional("VAT", default=True): vol.Boolean,
        vol.Optional("precision", default=3): cv.positive_int,
        vol.Optional("low_price_cutoff", default=1.0): cv.small_float,
        vol.Optional("price_type", default="kWh"): vol.In(list(_PRICE_IN.keys())),
    }
)


def setup_platform(hass, config, add_devices, discovery_info=None) -> None:
    """Setup the damn platform using yaml."""
    _LOGGER.info("setup_platform %s", config)
    _LOGGER.info("pendulum default timezone %s", pendulum.now().timezone_name)
    _LOGGER.info("timezone set in ha %r", hass.config.time_zone)
    region = config.get(CONF_REGION)
    friendly_name = config.get("friendly_name")
    price_type = config.get("price_type")
    precision = config.get("precision")
    low_price_cutoff = config.get("low_price_cutoff")
    currency = config.get("currency")
    vat = config.get("VAT")
    api = hass.data[DOMAIN]
    sensor = NordpoolSensor(
        friendly_name,
        region,
        price_type,
        precision,
        low_price_cutoff,
        currency,
        vat,
        api,
    )

    add_devices([sensor])


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Setup sensor platform for the ui"""
    config = config_entry.data
    region = config.get(CONF_REGION)
    friendly_name = config.get("friendly_name")
    price_type = config.get("price_type")
    precision = config.get("precision")
    low_price_cutoff = config.get("low_price_cutoff")
    currency = config.get("currency")
    vat = config.get("VAT")
    api = hass.data[DOMAIN]
    sensor = NordpoolSensor(
        friendly_name,
        region,
        price_type,
        precision,
        low_price_cutoff,
        currency,
        vat,
        api,
    )
    async_add_devices([sensor])


class NordpoolSensor(Entity):
    def __init__(
        self,
        friendly_name,
        area,
        price_type,
        precision,
        low_price_cutoff,
        currency,
        vat,
        api,
    ) -> None:
        self._friendly_name = friendly_name or "%s %s %s" % (
            DEFAULT_NAME,
            price_type,
            area,
        )
        self._area = area
        self._currency = currency or _REGIONS[area][0]
        self._price_type = price_type
        self._precision = precision
        self._low_price_cutoff = low_price_cutoff
        self._api = api

        if vat:
            self._vat = _REGIONS[area][2]
        else:
            self._vat = 0

        # Price by current hour.
        self._current_price = None

        # Holds the data for today and morrow.
        self._data_today = None
        self._data_tomorrow = None

        # Values for the day
        self._average = None
        self._max = None
        self._min = None
        self._off_peak_1 = None
        self._off_peak_2 = None
        self._peak = None

        # To control the updates.
        self._last_update_hourly = None
        self._last_tick = None

    @property
    def name(self) -> str:
        return self.unique_id

    @property
    def friendly_name(self) -> str:
        return self._friendly_name

    @property
    def icon(self) -> str:
        return "mdi:flash"

    @property
    def unit(self) -> str:
        return self._price_type

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement this sensor expresses itself in."""
        return "%s/%s" % (self._currency, self._price_type)

    @property
    def unique_id(self):
        name = "nordpool_%s_%s_%s_%s_%s_%s" % (
            self._price_type,
            self._area,
            self._currency,
            self._precision,
            self._low_price_cutoff,
            self._vat,
        )
        name = name.lower().replace(".", "")
        return name

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": DOMAIN,
        }

    @property
    def state(self) -> float:
        return self.current_price

    @property
    def low_price(self) -> bool:
        """Check if the price is lower then avg depending on settings"""
        return (
            self.current_price < self._average * self._low_price_cutoff
            if self.current_price and self._average
            else None
        )

    def _calc_price(self, value=None) -> float:
        """Calculate price based on the users settings."""
        if value is None:
            value = self._current_price

        if value is None or math.isinf(value):
            _LOGGER.info("api returned junk infinty %s", value)
            return None

        # The api returns prices in MWh
        if self._price_type == "MWh":
            price = value * float(1 + self._vat)
        else:
            price = value / _PRICE_IN[self._price_type] * (float(1 + self._vat))

        return round(price, self._precision)

    def _update(self, data) -> None:
        """Set attrs."""
        _LOGGER.debug("Called _update setting attrs for the day")

        if has_junk(data):
            _LOGGER.info("It was junk infinty in api response, fixed it.")
            d = extract_attrs(data.get("values"))
            data.update(d)

        # we could check for peaks here.
        self._average = self._calc_price(data.get("Average"))
        self._min = self._calc_price(data.get("Min"))
        self._max = self._calc_price(data.get("Max"))
        self._off_peak_1 = self._calc_price(data.get("Off-peak 1"))
        self._off_peak_2 = self._calc_price(data.get("Off-peak 2"))
        self._peak = self._calc_price(data.get("Peak"))

    @property
    def current_price(self) -> float:
        return self._calc_price()

    def _someday(self, data) -> list:
        """The data is already sorted in the xml,
           but i dont trust that to continue forever. Thats why we sort it ourselfs."""
        if data is None:
            return []

        # All the time in the api is returned in utc
        # convert this to local time.
        tz = pendulum.now().timezone_name
        local_times = []
        for item in data.get("values", []):
            i = {
                "start": pendulum.instance(item["start"]).in_timezone(tz),
                "end": pendulum.instance(item["end"]).in_timezone(tz),
                "value": item["value"],
            }

            local_times.append(i)

        data["values"] = local_times

        return sorted(data.get("values", []), key=itemgetter("start"))

    @property
    def today(self) -> list:
        """Get todays prices

        Returns:
            list: sorted list where today[0] is the price of hour 00.00 - 01.00
        """
        return [
            self._calc_price(i["value"]) for i in self._someday(self._data_today) if i
        ]

    @property
    def tomorrow(self) -> list:
        """Get tomorrows prices

        Returns:
            list: sorted where tomorrow[0] is the price of hour 00.00 - 01.00 etc.
        """
        return [
            self._calc_price(i["value"])
            for i in self._someday(self._data_tomorrow)
            if i
        ]

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
            "unit": self.unit,
            "currency": self._currency,
            "country": _REGIONS[self._area][1],
            "region": self._area,
            "low price": self.low_price,
            "today": self.today,
            "tomorrow": self.tomorrow,
        }

    def _update_current_price(self) -> None:
        """ update the current price (price this hour)"""
        local_now = pendulum.now()

        if self._last_update_hourly is None or is_new(self._last_update_hourly, "hour"):
            data = self._api.today(self._area, self._currency)
            if data:
                for item in self._someday(data):
                    if item["start"] == local_now.start_of("hour"):
                        self._current_price = item["value"]
                        self._last_update_hourly = local_now
                        _LOGGER.debug("Updated _current_price %s", item["value"])
            else:
                _LOGGER.info("Cant update _update_current_price because it was no data")
        else:
            _LOGGER.debug("Tried to update the hourly price but it wasnt a new hour.")

    def update(self) -> None:
        """Ideally we should just pull from the api all the time but since
           se shouldnt do any io inside any other methods we store the data
           in self._data_today and self._data_tomorrow.
        """
        if self._last_tick is None:
            self._last_tick = pendulum.now()

        if self._data_today is None:
            _LOGGER.debug("NordpoolSensor _data_today is none, trying to fetch it.")
            today = self._api.today(self._area, self._currency)
            if today:
                self._data_today = today
                self._update(today)

        if self._data_tomorrow is None:
            _LOGGER.debug("NordpoolSensor _data_tomorrow is none, trying to fetch it.")
            tomorrow = self._api.tomorrow(self._area, self._currency)
            if tomorrow:
                self._data_tomorrow = tomorrow

        if is_new(self._last_tick, typ="day"):

            # No need to update if we got the info we need
            if self._data_tomorrow is not None:
                self._data_today = self._data_tomorrow
                self._update(self._data_today)
                self._data_tomorrow = None
            else:
                today = self._api.today(self._area, self._currency)
                if today:
                    self._data_today = today
                    self._update(today)

        # Updates the current for this hour.
        self._update_current_price()

        # Lets just pull data from the api
        # it will only do io if need.
        tomorrow = self._api.tomorrow(self._area, self._currency)
        if tomorrow:
            self._data_tomorrow = tomorrow

        self._last_tick = pendulum.now()
