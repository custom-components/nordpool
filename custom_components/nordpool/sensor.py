import logging
import math
from operator import itemgetter
from statistics import mean

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_REGION
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.template import Template, attach
from homeassistant.util import dt as dt_utils
from jinja2 import pass_context

from . import DOMAIN, EVENT_NEW_DATA, _REGIONS
from .misc import extract_attrs, is_new, start_of

_LOGGER = logging.getLogger(__name__)

_CENT_MULTIPLIER = 100
_PRICE_IN = {"kWh": 1000, "MWh": 0, "Wh": 1000 * 1000}


# Needed incase a user wants the prices in non local currency
_CURRENCY_TO_LOCAL = {"DKK": "Kr", "NOK": "Kr", "SEK": "Kr", "EUR": "€"}
_CURRENTY_TO_CENTS = {"DKK": "Øre", "NOK": "Øre", "SEK": "Öre", "EUR": "c"}

DEFAULT_CURRENCY = "NOK"
DEFAULT_REGION = "Kr.sand"
DEFAULT_NAME = "Elspot"


DEFAULT_TEMPLATE = "{{0.0|float}}"


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
    }
)


def _dry_setup(hass, config, add_devices, discovery_info=None):
    """Setup the damn platform using yaml."""
    _LOGGER.debug("Dumping config %r", config)
    _LOGGER.debug("timezone set in ha %r", hass.config.time_zone)
    region = config.get(CONF_REGION)
    friendly_name = config.get("friendly_name", "")
    price_type = config.get("price_type")
    precision = config.get("precision")
    low_price_cutoff = config.get("low_price_cutoff")
    currency = config.get("currency")
    vat = config.get("VAT")
    use_cents = config.get("price_in_cents")
    ad_template = config.get("additional_costs")
    api = hass.data[DOMAIN]
    api.add_area(region)
    sensor = NordpoolSensor(
        friendly_name,
        region,
        price_type,
        precision,
        low_price_cutoff,
        currency,
        vat,
        use_cents,
        api,
        ad_template,
        hass,
    )

    add_devices([sensor])


async def async_setup_platform(hass, config, add_devices, discovery_info=None) -> None:
    """Setup for yaml."""
    _dry_setup(hass, config, add_devices)
    return True


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Setup sensor platform for the ui"""
    config = config_entry.data
    _dry_setup(hass, config, async_add_devices)
    return True


class NordpoolSensor(Entity):
    """Sensor for nordpool"""

    def __init__(
        self,
        friendly_name,
        area,
        price_type,
        precision,
        low_price_cutoff,
        currency,
        vat,
        use_cents,
        api,
        ad_template,
        hass,
    ) -> None:
        # friendly_name is ignored as it never worked.
        # rename the sensor in the ui if you dont like the name.
        self._area = area
        self._currency = currency or _REGIONS[area][0]
        self._price_type = price_type
        self._precision = precision
        self._low_price_cutoff = low_price_cutoff
        self._use_cents = use_cents
        self._api = api
        self._ad_template = ad_template
        self._hass = hass

        if vat is True:
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

        # Check incase the sensor was setup using config flow.
        # This blow up if the template isnt valid.
        if not isinstance(self._ad_template, Template):
            if self._ad_template in (None, ""):
                self._ad_template = DEFAULT_TEMPLATE
            self._ad_template = cv.template(self._ad_template)
        # check for yaml setup.
        else:
            if self._ad_template.template in ("", None):
                self._ad_template = cv.template(DEFAULT_TEMPLATE)

        attach(self._hass, self._ad_template)

        # To control the updates.
        self._last_tick = None
        self._cbs = []

    @property
    def name(self) -> str:
        return self.unique_id

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def icon(self) -> str:
        return "mdi:flash"

    @property
    def unit(self) -> str:
        return self._price_type

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement this sensor expresses itself in."""
        _currency = self._currency
        if self._use_cents is True:
            # Convert unit of measurement to cents based on chosen currency
            _currency = _CURRENTY_TO_CENTS[_currency]
        return "%s/%s" % (_currency, self._price_type)

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

    def _calc_price(self, value=None, fake_dt=None) -> float:
        """Calculate price based on the users settings."""
        if value is None:
            value = self._current_price

        if value is None or math.isinf(value):
            # _LOGGER.debug("api returned junk infinty %s", value)
            return None

        # Used to inject the current hour.
        # so template can be simplified using now
        if fake_dt is not None:

            def faker():
                def inner(*args, **kwargs):
                    return fake_dt

                return pass_context(inner)

            template_value = self._ad_template.async_render(now=faker())
        else:
            template_value = self._ad_template.async_render()

        # The api returns prices in MWh
        if self._price_type in ("MWh", "mWh"):
            price = template_value / 1000 + value * float(1 + self._vat)
        else:
            price = template_value + value / _PRICE_IN[self._price_type] * (
                float(1 + self._vat)
            )

        # Convert price to cents if specified by the user.
        if self._use_cents:
            price = price * _CENT_MULTIPLIER

        return round(price, self._precision)

    def _update(self, data) -> None:
        """Set attrs."""
        _LOGGER.debug("Called _update setting attrs for the day")

        d = extract_attrs(data.get("values"))
        data.update(d)

        if self._ad_template.template == DEFAULT_TEMPLATE:
            self._average = self._calc_price(data.get("Average"))
            self._min = self._calc_price(data.get("Min"))
            self._max = self._calc_price(data.get("Max"))
            self._off_peak_1 = self._calc_price(data.get("Off-peak 1"))
            self._off_peak_2 = self._calc_price(data.get("Off-peak 2"))
            self._peak = self._calc_price(data.get("Peak"))
        else:
            data = sorted(data.get("values"), key=itemgetter("start"))
            formatted_prices = [
                self._calc_price(
                    i.get("value"), fake_dt=dt_utils.as_local(i.get("start"))
                )
                for i in data
                if i.get("value")
            ]
            offpeak1 = formatted_prices[0:8]
            peak = formatted_prices[9:17]
            offpeak2 = formatted_prices[20:]

            self._peak = mean(peak)
            self._off_peak_1 = mean(offpeak1)
            self._off_peak_2 = mean(offpeak2)
            self._average = mean(formatted_prices)
            self._min = min(formatted_prices)
            self._max = max(formatted_prices)

    @property
    def current_price(self) -> float:
        """The calculated price for the current hour"""
        res = self._calc_price()
        return res

    def _someday(self, data) -> list:
        """The data is already sorted in the xml,
        but i dont trust that to continue forever. Thats why we sort it ourselfs."""
        if data is None:
            return []

        local_times = []
        for item in data.get("values", []):
            i = {
                "start": dt_utils.as_local(item["start"]),
                "end": dt_utils.as_local(item["end"]),
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
            self._calc_price(i["value"], fake_dt=i["start"])
            for i in self._someday(self._data_today)
            if i is not None
        ]

    @property
    def tomorrow(self) -> list:
        """Get tomorrows prices

        Returns:
            list: sorted where tomorrow[0] is the price of hour 00.00 - 01.00 etc.
        """
        if self._data_tomorrow is None:
            return []

        return [
            self._calc_price(i["value"], fake_dt=i["start"])
            for i in self._someday(self._data_tomorrow)
            if i is not None
        ]

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "current_price": self.current_price,
            "average": self._average,
            "off_peak_1": self._off_peak_1,
            "off_peak_2": self._off_peak_2,
            "peak": self._peak,
            "min": self._min,
            "max": self._max,
            "unit": self.unit,
            "currency": self._currency,
            "country": _REGIONS[self._area][1],
            "region": self._area,
            "low price": self.low_price,
            "tomorrow_valid": self.tomorrow_valid,
            "today": self.today,
            "tomorrow": self.tomorrow,
            "raw_today": self.raw_today,
            "raw_tomorrow": self.raw_tomorrow,
        }

    def _add_raw(self, data):
        result = []
        for res in self._someday(data):
            item = {
                "start": res["start"],
                "end": res["end"],
                "value": self._calc_price(res["value"], fake_dt=res["start"]),
            }
            result.append(item)
        return result

    @property
    def raw_today(self):
        """Raw values for today"""
        return self._add_raw(self._data_today)

    @property
    def raw_tomorrow(self):
        """Raw values for tomorrow"""
        return self._add_raw(self._data_tomorrow)

    @property
    def tomorrow_valid(self):
        """Check if the data for tomorrow is valid"""
        # todo this should be improved
        return len([i for i in self.tomorrow if i is not None]) >= 20

    async def _update_current_price(self) -> None:
        """update the current price (price this hour)"""
        local_now = dt_utils.now()

        data = await self._api.today(self._area, self._currency)
        if data:
            for item in self._someday(data):
                if item["start"] == start_of(local_now, "hour"):
                    self._current_price = item["value"]
                    _LOGGER.debug(
                        "Updated %s _current_price %s", self.name, item["value"]
                    )
        else:
            _LOGGER.debug("Cant update _update_current_price because it was no data")

    async def check_stuff(self) -> None:
        """Cb to do some house keeping, called every hour to get the current hours price"""
        _LOGGER.debug("called check_stuff")
        if self._last_tick is None:
            self._last_tick = dt_utils.now()

        if self._data_today is None:
            _LOGGER.debug("NordpoolSensor _data_today is none, trying to fetch it.")
            today = await self._api.today(self._area, self._currency)
            if today:
                self._data_today = today
                self._update(today)

        if self._data_tomorrow is None:
            _LOGGER.debug("NordpoolSensor _data_tomorrow is none, trying to fetch it.")
            tomorrow = await self._api.tomorrow(self._area, self._currency)
            if tomorrow:
                self._data_tomorrow = tomorrow

        if is_new(self._last_tick, typ="day"):
            if self._data_tomorrow is not None:
                _LOGGER.debug("Setting tomorrows data as today and clearing tomorrow.")
                self._data_today = self._data_tomorrow
                self._data_tomorrow = None
                self._update(self._data_today)

            else:
                today = await self._api.today(self._area, self._currency)
                self._data_tomorrow = None
                if today:
                    self._data_today = today
                    self._update(today)

        # Updates the current for this hour.
        await self._update_current_price()

        tomorrow = await self._api.tomorrow(self._area, self._currency)
        if tomorrow:
            self._data_tomorrow = tomorrow

        self._last_tick = dt_utils.now()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()
        async_dispatcher_connect(self._api._hass, EVENT_NEW_DATA, self.check_stuff)

        # We want to run the first request in the background so the integration get added to ha
        # and don't timeout because of HTTP retries because of missing data/api issues.
        self._hass.async_create_task(self.check_stuff())

    # async def async_will_remove_from_hass(self):
    #     """This needs some testing.."""
    #     for cb in self._cbs:
    #         self._api._hass.bus._async_remove_listener(EVENT_TIME_CHANGED, cb)
