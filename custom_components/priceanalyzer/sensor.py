import logging
import math
from datetime import datetime
from operator import itemgetter
from statistics import mean

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_REGION, EVENT_TIME_CHANGED
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.template import Template, attach
from homeassistant.util import dt as dt_utils
from jinja2 import pass_context

from . import DOMAIN, EVENT_NEW_DATA
from .misc import extract_attrs, has_junk, is_new, start_of

_LOGGER = logging.getLogger(__name__)

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
    _dry_setup(hass, config, add_devices)
    return True


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Setup sensor platform for the ui"""
    config = config_entry.data
    _dry_setup(hass, config, async_add_devices)
    return True


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
        use_cents,
        api,
        ad_template,
        hass,
    ) -> None:
        # friendly_name is ignored as it never worked.
        # rename the sensor in the ui if you dont like the name.
        self._attr_name = friendly_name
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

        self._current_hour = None
        self._today_calculated = None
        self._tomorrow_calculated = None
        

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
        self._percent_threshold = None
        self._diff = None
        self._ten_cheapest_today = None
    

        # Values for tomorrow
        self._average_tomorrow = None
        self._max_tomorrow = None
        self._min_tomorrow = None
        self._off_peak_1_tomorrow = None
        self._off_peak_2_tomorrow = None
        self._peak_tomorrow = None
        self._percent_threshold_tomorrow = None
        self._diff_tomorrow = None
        self._ten_cheapest_tomorrow = None



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
        return 'Price Analyzer'

    @property
    def should_poll(self):
        """No need to poll. Coordinator notifies entity of updates."""
        return False

    @property
    def icon(self) -> str:
        return "mdi:sine-wave"

    @property
    def unit(self) -> str:
        return self._price_type

    @property
    def unit_of_measurement(self) -> str:
        return '°C'

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
        if self.current_hour:
            return self.current_hour['temperature_correction']
        else:
            return None
        # if self._today_calculated != None:
        #     now = datetime.now()
        #     return self._today_calculated[now.hour]['temperature_correction']
        # else:
        #     return None

    @property
    def low_price(self) -> bool:
        """Check if the price is lower then avg depending on settings"""
        return (
            self.current_price < self._average * self._low_price_cutoff
            if self.current_price and self._average
            else None

        )

    def is_price_low_price(self, price) -> bool:
        """Check if the price is lower then avg depending on settings"""
        return (
            price < self._average * self._low_price_cutoff
            if price and self._average
            else None
        )

    def _is_gaining(self, hour,  now, price_now, price_next_hour, price_next_hour2, price_next_hour3, is_tomorrow) -> bool:        
        threshold = self._percent_threshold_tomorrow if is_tomorrow else self._percent_threshold
        percent_threshold = (1 - float(threshold))
        return ((price_now / price_next_hour) < percent_threshold) or ((price_now / price_next_hour2) < percent_threshold)# or ((price_now / price_next_hour3) < percent_threshold)

    def _is_falling(self, hour,  now, price_now, price_next_hour, price_next_hour2, price_next_hour3, is_tomorrow) -> bool:        
        threshold = self._percent_threshold_tomorrow if is_tomorrow else self._percent_threshold
        percent_threshold = (1 + float(threshold))
        return ((price_now / price_next_hour) > percent_threshold) or ((price_now / price_next_hour2) > percent_threshold) or ((price_now / price_next_hour3) > percent_threshold)


    def _get_temperature_correction(self, now, is_gaining, is_falling,is_max, is_low_price, is_over_peak, is_tomorrow, is_over_average) -> float:
        #pricedifference = min / max # property
        #Todo, is_garinnig and is_falling is missing threshold, else alles good i think.
        
        diff = self._diff_tomorrow if is_tomorrow else self._diff
        if(diff < 1.5):
            return 0

        price_now = self._calc_price(now["value"], fake_dt=now["start"])
        is_over_off_peak_1 = price_now > (self._off_peak_1_tomorrow if is_tomorrow else self._off_peak_1)

        if is_max:
            return -1
        elif is_gaining:
        #elif (is_over_peak == False and is_gaining == True):
        #elif (is_low_price == True and is_gaining == True):
            return 1
        elif is_falling and is_over_average == True:
            return -1
        elif is_low_price and (is_gaining == False or is_falling): 
            return 0
        elif (is_over_peak and is_falling) or is_over_off_peak_1:
            return -1
        else:
            return 0

        
        
    def get_hour(self, hour, is_tomorrow):
        if is_tomorrow == False and (hour < len(self._someday(self._data_today))):
            return self._someday(self._data_today)[hour]
        elif is_tomorrow == False and self.tomorrow_valid and (hour-24 < len(self._someday(self._data_tomorrow))):
            return self._someday(self._data_tomorrow)[hour-24]
        elif is_tomorrow and (hour < len(self._someday(self._data_tomorrow))):
            return self._someday(self._data_tomorrow)[hour]
        else:
            return None


    def _calc_price(self, value=None, fake_dt=None) -> float:
        """Calculate price based on the users settings."""
        if value is None:
            value = self._current_price

        if value is None or math.isinf(value):
            _LOGGER.debug("api returned junk infinty %s", value)
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

        # if has_junk(data):
        #    # _LOGGER.debug("It was junk infinity in api response, fixed it.")
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
            
            self._add_raw_calculated(data,False)
            


    def _update_tomorrow(self, data) -> None:

        if self._api.tomorrow_valid() == False:
            return
        """Set attrs."""
        _LOGGER.debug("Called _update setting attrs for the day")

        # if has_junk(data):
        #    # _LOGGER.debug("It was junk infinity in api response, fixed it.")
        d = extract_attrs(data.get("values"))
        data.update(d)

        if self._ad_template.template == DEFAULT_TEMPLATE:
            self._average_tomorrow = self._calc_price(data.get("Average"))
            self._min_tomorrow = self._calc_price(data.get("Min"))
            self._max_tomorrow = self._calc_price(data.get("Max"))
            self._off_peak_1_tomorrow = self._calc_price(data.get("Off-peak 1"))
            self._off_peak_2_tomorrow = self._calc_price(data.get("Off-peak 2"))
            self._peak_tomorrow = self._calc_price(data.get("Peak"))
        else:
            data = sorted(data.get("values"), key=itemgetter("start"))
            formatted_prices = [
                self._calc_price(
                    i.get("value"), fake_dt=dt_utils.as_local(i.get("start"))
                )
                for i in data
            ]
            
            if formatted_prices[0] != None: 
                offpeak1 = formatted_prices[0:8]
                peak = formatted_prices[9:17]
                offpeak2 = formatted_prices[20:]
                
                self._peak_tomorrow = mean(peak)
                self._off_peak_1_tomorrow = mean(offpeak1)
                self._off_peak_2_tomorrow = mean(offpeak2)
                self._average_tomorrow = mean(formatted_prices)
                self._min_tomorrow = min(formatted_prices)
                self._max_tomorrow = max(formatted_prices)
                self._add_raw_calculated(data,True)



    @property
    def current_price(self) -> float:
        res = self._calc_price()
        # _LOGGER.debug("Current hours price for %s is %s", self.name, res)
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
            if i
        ]

    @property
    def tomorrow(self) -> list:
        """Get tomorrows prices

        Returns:
            list: sorted where tomorrow[0] is the price of hour 00.00 - 01.00 etc.
        """
        return [
            self._calc_price(i["value"], fake_dt=i["start"])
            for i in self._someday(self._data_tomorrow)
            if i
        ]

    @property
    def current_hour(self) -> list:
        if self._today_calculated != None:
            now = datetime.now()
            return self._today_calculated[now.hour]
        else:
            return []
        
    @property
    def extra_state_attributes(self) -> dict:
        now = datetime.now()

        
        
        return {
            "display_name" : self._attr_name,
            "low price": self.low_price,
            "tomorrow_valid": self.tomorrow_valid,
            'max': self._max,
            'min': self._min,
            'peak': self._peak,
            'off_peak_1': self._off_peak_1,
            'off_peak_2': self._off_peak_2,
            'average': self._average,
            "current_hour": self.current_hour,
            "raw_today": self.today_calculated,
            "raw_tomorrow": self.tomorrow_calculated,
            "ten_cheapest_today": self._ten_cheapest_today,
            "ten_cheapest_tomorrow": self._ten_cheapest_tomorrow,
        }


    def _format_time(self, data):
        local_times = []
        for item in data:
            i = {
                "start": dt_utils.as_local(item["start"]),
                "end": dt_utils.as_local(item["end"]),
                "value": item["value"],
            }

            local_times.append(i)

        return local_times


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


    def _set_cheapest_hours_today(self):
        if self._data_today != None and len(self._data_today.get("values")):
            data = sorted(self._data_today.get("values"), key=itemgetter("value"))
            formatted_prices = [
                {
                    'start' : i.get('start'),
                    'end' : i.get('end'),
                    'value' : self._calc_price(
                        i.get("value"), fake_dt=dt_utils.as_local(i.get("start"))
                        )
                }
                for i in data
            ]
            
            ten_cheapest_today = formatted_prices[:10]
            self._ten_cheapest_today = ten_cheapest_today
            
    def _set_cheapest_hours_tomorrow(self):
        if self._data_tomorrow != None and len(self._data_tomorrow.get("values")):
            data = sorted(self._data_tomorrow.get("values"), key=itemgetter("value"))
            formatted_prices = [
                {
                    'start' : i.get('start'),
                    'end' : i.get('end'),
                    'value' : self._calc_price(
                        i.get("value"), fake_dt=dt_utils.as_local(i.get("start"))
                        )
                }
                for i in data
            ]
            
            ten_cheapest_tomorrow = formatted_prices[:10]
            self._ten_cheapest_tomorrow = ten_cheapest_tomorrow


    def _add_raw_calculated(self, data, is_tomorrow):
        
        if is_tomorrow and self.tomorrow_valid == False:
            return []

        result = []
        hour = 0
        

        #{%-set percentThreshold = ((nordpool.attributes.min / nordpool.attributes.max) - 1) -%}
        #{% set percentThreshold = (percentThreshold / 4) * -1 %}
            
        if is_tomorrow == False:
            difference = ((self._min / self._max) - 1)
            self._percent_threshold = ((difference / 4) * -1)
            self._diff = self._max / self._min
            self._set_cheapest_hours_today()


        if self._api.tomorrow_valid() == True and is_tomorrow == True:
            max_tomorrow = self._max_tomorrow
            min_tomorrow = self._min_tomorrow
            difference = ((min_tomorrow / max_tomorrow) - 1)
            self._percent_threshold_tomorrow = ((difference / 4) * -1)    
            self._diff_tomorrow = max_tomorrow / min_tomorrow
            self._set_cheapest_hours_tomorrow()


        data = self._format_time(data)
        peak = self._peak_tomorrow if is_tomorrow else self._peak
        max_price = self._max_tomorrow if is_tomorrow else self._max
        average = self._average_tomorrow if is_tomorrow else self._average
        local_now = dt_utils.now()
        for res in data:

            price_now = float(self._calc_price(res["value"], fake_dt=res["start"]))
            is_max = price_now == max_price
            is_low_price = price_now < average * self._low_price_cutoff
            is_over_peak = price_now > peak
            is_over_average = price_now > average

            # item = {
            #     "data_today": self._data_today,
            #     }
            # result.append(item)
            # continue

            #todo 'value' keyerror in calc_price.

            #if price_now == None:
            #    return None

            next_hour = self.get_hour(hour+1, is_tomorrow)
            next_hour2 = self.get_hour(hour+2, is_tomorrow)
            next_hour3 = self.get_hour(hour+3, is_tomorrow)

            if next_hour != None and next_hour2 != None and next_hour3 != None:    
                
                price_next_hour3 = self._calc_price(next_hour3["value"], fake_dt=next_hour3["start"]) or price_now
                price_next_hour2 = self._calc_price(next_hour2["value"], fake_dt=next_hour2["start"]) or price_now
                price_next_hour = self._calc_price(next_hour["value"], fake_dt=next_hour["start"]) or price_now
                is_gaining = self._is_gaining(hour, res, price_now, price_next_hour, price_next_hour2, price_next_hour3, is_tomorrow)
                is_falling = self._is_falling(hour, res, price_now, price_next_hour, price_next_hour2, price_next_hour3, is_tomorrow)
                percent_diff = price_next_hour / price_now
            else:
                is_gaining = None
                is_falling = None
                price_next_hour = None
                percent_diff = None

            item = {
                "start": res["start"],
                "end": res["end"],
                "value": price_now,
                "price_next_hour": price_next_hour,
                "is_gaining": is_gaining,
                "is_falling": is_falling,
                'is_max': is_max,
                'is_low_price': is_low_price,
                'is_over_peak' : is_over_peak,
                'is_over_average': is_over_average
            }

            item['is_ten_cheapest'] = self._is_ten_cheapest(item,is_tomorrow)
            item['is_five_most_expensive'] = self._is_five_most_expensive(item, is_tomorrow)
            item["temperature_correction"] = self._get_temperature_correction(item, is_gaining,is_falling, is_max, is_low_price, is_over_peak, is_tomorrow, is_over_average)
            hour += 1
            if item["start"] == start_of(local_now, "hour"):
                self._current_hour = item

            result.append(item)

        if is_tomorrow == False:
            self._today_calculated = result
        else:
            self._tomorrow_calculated = result
            
        return result

    def _is_ten_cheapest(self, item, is_tomorrow):
        ten_cheapest = self._ten_cheapest_tomorrow if is_tomorrow else self._ten_cheapest_today
        if ten_cheapest == None:
            return False
        
        if any(obj['start'] == item['start'] for obj in ten_cheapest ):
            return True
        return False

    def _is_five_most_expensive(self, item, is_tomorrow):
        five_most_expensive = self._get_five_most_expensive_hours(is_tomorrow)
        if any(obj['start'] == item['start'] for obj in five_most_expensive):
            return True
        return False

    def _get_five_most_expensive_hours(self, is_tomorrow):
        hours = self._data_tomorrow if is_tomorrow else self._data_today
        if len(hours.get("values")):
            data = sorted(hours.get("values"), key=itemgetter("value"), reverse=True)
            formatted_prices = [
                {
                    'start' : i.get('start'),
                    'end' : i.get('end'),
                    'value' : self._calc_price(
                        i.get("value"), fake_dt=dt_utils.as_local(i.get("start"))
                        )
                }
                for i in data
            ]
        five_most_expensive = formatted_prices[:5]
        return five_most_expensive
        
    @property
    def raw_today(self):
        return self._add_raw(self._data_today)

    @property
    def raw_tomorrow(self):
        return self._add_raw(self._data_tomorrow)

    @property
    def today_calculated(self):
        if self._today_calculated != None and len(self._today_calculated):
            return self._today_calculated
        else:
            return []

    @property
    def tomorrow_calculated(self):
        if self._tomorrow_calculated != None and len(self._tomorrow_calculated):
            return self._tomorrow_calculated
        else:
            return []

    @property
    def tomorrow_valid(self):
        return self._api.tomorrow_valid()
        
        
    @property
    def tomorrow_loaded(self):
        return isinstance(self._data_tomorrow, list) and len(self._data_tomorrow)

    async def _update_current_price(self) -> None:
        """ update the current price (price this hour)"""
        local_now = dt_utils.now()

        data = await self._api.today(self._area, self._currency)
        if data:
            for item in self._someday(data):
                if item["start"] == start_of(local_now, "hour"):
                    # _LOGGER.info("start %s local_now %s", item["start"], start_of(local_now, "hour"))
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


        if self._data_tomorrow is None or len(self._data_tomorrow.get("values")) < 1:
            _LOGGER.debug("NordpoolSensor _data_tomorrow is none, trying to fetch it.")
            tomorrow = await self._api.tomorrow(self._area, self._currency)
            if tomorrow:
                self._data_tomorrow = tomorrow
                self._update_tomorrow(tomorrow)


        if self._data_today is None:
            _LOGGER.debug("NordpoolSensor _data_today is none, trying to fetch it.")
            today = await self._api.today(self._area, self._currency)
            if today:
                self._data_today = today
                self._update(today)

                

        # We can just check if this is the first hour.

        if is_new(self._last_tick, typ="day"):
            # if now.hour == 0:
            # No need to update if we got the info we need
            if self._data_tomorrow is not None:
                self._data_today = self._data_tomorrow
                self.today_calculated = self._tomorrow_calculated
                self._average = self._average_tomorrow
                self._max = self._max_tomorrow
                self._min = self._min_tomorrow
                self._off_peak_1 = self._off_peak_1_tomorrow
                self._off_peak_2 = self._off_peak_2_tomorrow
                self._peak = self._peak_tomorrow
                self._percent_threshold = self._percent_threshold_tomorrow
                self._diff = self._diff_tomorrow
                self._ten_cheapest_today = self._ten_cheapest_tomorrow
                
                self._update(self._data_today)
                self._data_tomorrow = None
            else:
                today = await self._api.today(self._area, self._currency)
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
        #self._data_today !== None and len(self._data_today.get("values")
        if self.tomorrow_valid and (self._tomorrow_calculated != None or len(self._tomorrow_calculated) < 1):
            self.check_stuff()

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        await super().async_added_to_hass()
        _LOGGER.debug("called async_added_to_hass %s", self.name)
        async_dispatcher_connect(self._api._hass, EVENT_NEW_DATA, self.check_stuff)

        await self.check_stuff()

    # async def async_will_remove_from_hass(self):
    #     """This needs some testing.."""
    #     for cb in self._cbs:
    #         self._api._hass.bus._async_remove_listener(EVENT_TIME_CHANGED, cb)
