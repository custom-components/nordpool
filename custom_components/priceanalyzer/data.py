import asyncio
import logging
import math
from datetime import datetime, timedelta, date
from operator import itemgetter
from statistics import mean

import aiohttp
import backoff
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import CONF_REGION
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_utils
from jinja2 import pass_context

from .const import DOMAIN, EVENT_NEW_DATA, _REGIONS, _PRICE_IN, EVENT_CHECKED_STUFF
from .misc import extract_attrs, has_junk, is_new, start_of

_LOGGER = logging.getLogger(__name__)

_CENT_MULTIPLIER = 100

DEFAULT_CURRENCY = "NOK"
DEFAULT_REGION = "Kr.sand"
DEFAULT_NAME = "Elspot"


DEFAULT_TEMPLATE = "{{0.01|float}}"


class Data():
    def __init__(
        self,
        friendly_name,
        area,
        price_type,
        low_price_cutoff,
        currency,
        vat,
        use_cents,
        api,
        ad_template,
        multiply_template,
        num_hours_to_boost,
        num_hours_to_save,
        percent_difference,
        hass,
        config,
        entry_id=None
    ) -> None:



        self._attr_name = friendly_name
        self._area = area
        self._currency = currency or _REGIONS[area][0]
        self._price_type = price_type

        self._low_price_cutoff = low_price_cutoff
        self._use_cents = use_cents
        self.api = api
        self._ad_template = ad_template
        self._multiply_template = multiply_template
        self._num_hours_to_boost = num_hours_to_boost
        self._num_hours_to_save = num_hours_to_save
        self._hass = hass
        self.percent_difference = percent_difference or 20
        self._config = config

        self._precision = 3

        if 'vat' in config.keys():
            self._vat = _REGIONS[area][2]
        else:
            self._vat = 0

        self._vat = _REGIONS[area][2]

        # Price by current period (hour or quarter).
        self._current_price = None

        self._current_period = None
        self._today_calculated = None
        self._tomorrow_calculated = None

        # Holds the data for today and morrow.
        self._data_today = None
        self._data_tomorrow = None

        # list with sensors that utilises data from this class.
        self._sensors = []

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
        self._five_cheapest_today = None
        self.small_price_difference_today = None
        self.small_price_difference_tomorrow = None
        self._cheapest_hours_in_future_sorted = []

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
        self._five_cheapest_tomorrow = None

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

        self._ad_template.hass = self._hass

        if not isinstance(self._multiply_template, Template):
            if self._multiply_template in (None, ""):
                self._multiply_template = 1
            self._multiply_template = cv.template(self._multiply_template)
        # check for yaml setup.
        else:
            if self._multiply_template.template in ("", None):
                self._multiply_template = cv.template(1)

        self._multiply_template.hass = self._hass

        self.multiply_template = multiply_template
        self._entry_id = entry_id

        # To control the updates.
        self._last_tick = None
        self._cbs = []

    @property
    def device_name(self) -> str:
        # If we have a friendly_name, use it to make the device name more descriptive
        if self._attr_name and self._attr_name.strip():
            return self._attr_name
        return 'Priceanalyzer ' + self._area

    @property
    def device_unique_id(self):
        # Include entry_id to make device unique for each entry
        # This allows multiple setups with the same region
        if self._entry_id:
            # Use entry_id as base for unique device ID
            name = "priceanalyzer_device_%s" % (self._entry_id,)
        else:
            # Fallback for backward compatibility
            name = "priceanalyzer_device_%s_%s_%s_%s_%s_%s" % (
                self._price_type,
                self._area,
                self._currency,
                self._precision,
                self._low_price_cutoff,
                self._vat,
            )
        name = name.lower().replace(".", "").replace("-", "_")
        return name

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_unique_id)},
            name=self.device_name,
            manufacturer=DOMAIN,
        )

    @property
    def low_price(self) -> bool:
        """Check if the price is lower then avg depending on settings"""
        return (
            self.current_price < self._average * self._low_price_cutoff
            if self.current_price and self._average and self._low_price_cutoff
            else None
        )

    @property
    def current_price(self) -> float:
        res = self._calc_price()
        # _LOGGER.debug("Current hours price for %s is %s", self.device_name, res)
        return res

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
    def current_hour(self) -> dict:
        return self._current_period

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
        return len([i for i in self.tomorrow if i not in (None, float("inf"))]) >= 23

    @property
    def tomorrow_loaded(self):
        return isinstance(self._data_tomorrow, list) and len(self._data_tomorrow)

    async def _update_current_price(self) -> None:
        """ update the current price (price this period)"""
        local_now = dt_utils.now()

        data = await self.api.today(self._area, self._currency)
        if data:
            # Use appropriate time resolution for current period matching
            time_resolution = self._config.get("time_resolution", "hourly")
            time_type = "quarter" if time_resolution == "quarterly" else "hour"
            for item in self._someday(data):
                if item["start"] == start_of(local_now, time_type):
                    self._current_price = item["value"]

    def _update_current_period(self) -> None:
        """Update _current_period to reflect the current time"""
        if not self._today_calculated:
            return
            
        local_now = dt_utils.now()
        for item in self._today_calculated:
            if item["start"] <= local_now < item["end"]:
                self._current_period = item
                break

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

    def is_price_low_price(self, price) -> bool:
        """Check if the price is lower then avg depending on settings"""
        return (
            price < self._average * self._low_price_cutoff
            if price and self._average
            else None
        )

    def get_price_for_hour(self, hour: int, is_tomorrow: bool) -> int:
        """Gets the price for a given hour

        Args:
            hour (int): The hour to get the price for
            is_tomorrow (bool): Whether the hour is tomorrow

        Returns:
            int: The price for the hour
        """
        if hour > 24 and is_tomorrow is False:
            hour = hour - 24
            is_tomorrow = False
        hour = self.get_hour(hour,is_tomorrow)
        if hour is not None:
            return self._calc_price(hour["value"], fake_dt=hour["start"])
        else:
            return None





    def _is_gaining(self, hour, is_tomorrow) -> bool:
        threshold = self._percent_threshold_tomorrow if is_tomorrow else self._percent_threshold
        percent_threshold = (1 - float(threshold))

        #TODO, The logic is not quite right yet, but is the same as before.
        # the more hours set, the less threshold will matter, as it will compare more hours with the same threshold
        # as we compare now price with the price in X hours.
        # the more hours, the more difference the price will be, probably.
        # can we still compare the price to the hour or two before, but save X hours before?

        price_now = self.get_price_for_hour(hour, is_tomorrow)
        if price_now is None:
            return False
        for i in reversed(range(self._num_hours_to_boost or 2)):
            y = i + 1
            next_hour = self.get_price_for_hour(hour + y,is_tomorrow)
            if next_hour is None:
                continue
            price_next = max([next_hour, 0.00001])
            if (price_now / price_next) < percent_threshold:
                return True
        return False

    def _is_falling(self, hour, is_tomorrow) -> bool:

        # Get the threshold value from the settings
        threshold = self._percent_threshold_tomorrow if is_tomorrow else self._percent_threshold
        percent_threshold = (1 + float(threshold))

        # Get the current price
        price_now = self.get_price_for_hour(hour, is_tomorrow)
        price_next_hour = self.get_price_for_hour(hour + 1 , is_tomorrow)
        if price_now is None:
            return False

        # Loop through the saved prices to see if any are greater than the threshold
        for i in reversed(range(self._num_hours_to_save or 2)):
            y = i + 1
            next_hour = self.get_price_for_hour(hour + y,is_tomorrow)
            if next_hour is None:
                continue
            price_next = max([next_hour, 0.00001])
            if (price_now / price_next) > percent_threshold: # and price_now > price_next_hour:
                return True
        return False


    def price_percent_to_average(self, item, is_tomorrow) -> float:
        """Price in percent to average price"""
        average = self._average if is_tomorrow else self._average_tomorrow
        if average is None:
            return None

        return round(item['value'] / average, 3)

    def _is_falling_alot_next_hour(self, item) -> bool:
        return item['price_next_hour'] is not None and ((item['price_next_hour'] / max([item['value'], 0.00001])) < 0.60)

    def _is_falling_alot_next_hours(self, item) -> bool:
        falling_alot_next_hour = item['price_next_hour'] is not None and (
            (item['price_next_hour'] / max([item['value'], 0.00001])) < 0.80)
        falling_alot_next_next_hour = item['price_in_2_hours'] is not None and (
            (item['price_in_2_hours'] / max([item['value'], 0.00001])) < 0.80)
        # todo hour after that as well.
        return falling_alot_next_hour or falling_alot_next_next_hour

    def _get_temperature_correction(self, item, is_tomorrow, reason=False):
        is_gaining = item['is_gaining']
        is_falling = item['is_falling']
        is_max = item['is_max']
        is_low_price = item['is_low_price']
        is_over_average = item['is_over_average']
        is_five_most_expensive = item['is_five_most_expensive']

        diff = self._diff_tomorrow if is_tomorrow else self._diff
        percent_difference = (self.percent_difference + 100) / 100

        max_price = self._max_tomorrow if is_tomorrow else self._max
        threshold = self._config.get('pa_price_before_active', "") or 0
        below_threshold = float(threshold) > max_price
        if below_threshold == True:
            if reason:
                return 'Max-price below threshold'
            return 0

        # TODO this calculation is not considering additional costs.
        if (diff < percent_difference):
            if reason:
                return 'Small difference'
            return 0

        price_now = max([item["value"], 0.00001])

        price_next_hour = float(
            item["price_next_hour"]) if item["price_next_hour"] is not None else price_now
        price_next_hour = max([price_next_hour, 0.00001])

        # TODO Check currency
        isprettycheap = price_now < 0.05

        # special handling for high price at end of day:
        if not is_tomorrow and item['start'].hour == 23 and item['price_next_hour'] is not None and (price_next_hour / price_now) < 0.80 and isprettycheap == False:
            if reason:
                return 'Price dropping tomorrow'
            return -1
        if is_max:
            if reason:
                return 'Is max'
            return -1
        elif self._is_falling_alot_next_hour(item) and isprettycheap == False:
            if reason:
                return 'Is falling alot next hour'
            return -1
        elif is_gaining and (price_now < price_next_hour) and (not is_five_most_expensive):
            if reason:
                return 'Is gaining, and not in five most expensive hours'
            return 1
        elif is_falling and is_low_price == False:
            if reason:
                return 'Is falling and not low price'
            return -1
        elif is_low_price and (not is_gaining or is_falling):
            if reason:
                return 'No need to correct.'
            return 0
        # TODO is_over_off_peak_1 is not considering additional costs i think, so this is wrong.
        # Nope, the case is that it's just set hours, and not considering
        # the actual price, so useless as is. Must still get the price, and just
        # add the additional costs to get it 'more right'?
        # elif (is_over_peak and is_falling) or is_over_off_peak_1:
        #     return -1
        else:
            if reason:
                return 'No need to correct..'
            return 0

    def _adjust_price_correction(self, price_correction, item):

        value = self._multiply_template.async_render(
            correction=price_correction, current_hour=item
        )
        # Seems like the template is rendered as a string if the number is complex
        # Just force it to be a float.
        if not isinstance(value, (int, float)):
            try:
                value = float(value)
            except (TypeError, ValueError):
                _LOGGER.exception(
                    "Failed to convert %s %s to float",
                    value,
                    type(value),
                )
                raise
        return value

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
            return 0


        def faker():
            def inner(*_, **__):
                return fake_dt or dt_utils.now()

            return pass_context(inner)

        price = value / _PRICE_IN[self._price_type] * (float(1 + self._vat))
        template_value = self._ad_template.async_render(
            now=faker(), current_price=price
        )

        # Seems like the template is rendered as a string if the number is complex
        # Just force it to be a float.
        if not isinstance(template_value, (int, float)):
            try:
                template_value = float(template_value)
            except (TypeError, ValueError):
                _LOGGER.exception(
                    "Failed to convert %s %s to float",
                    template_value,
                    type(template_value),
                )
                raise

        self._additional_costs_value = template_value
        try:
            # If the price is negative, subtract the additional costs from the price
            template_value = abs(
                template_value) if price < 0 else template_value
            price += template_value
        except Exception:
            _LOGGER.debug(
                "price %s template value %s type %s dt %s current_price %s ",
                price,
                template_value,
                type(template_value),
                fake_dt,
                self._current_price,
            )
            raise

        # Convert price to cents if specified by the user.
        if self._use_cents:
            price = price * _CENT_MULTIPLIER

        return round(price, self._precision)

    def _update(self, data) -> None:
        """Set attrs."""
        _LOGGER.debug(
            "Called _update setting attrs for the day for %s", self._area)

        d = extract_attrs(data.get("values"))
        data.update(d)

        #TODO, cant use it like this, since  we don't know the time, and therefore not the template value.
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
        self._add_raw_calculated(False)

    def _update_tomorrow(self, data) -> None:

        if not self.api.tomorrow_valid():
            return
        """Set attrs."""
        _LOGGER.debug("Called _update setting attrs for tomorrow")

        d = extract_attrs(data.get("values"))
        data.update(d)

        if self._ad_template.template == DEFAULT_TEMPLATE:
            self._average_tomorrow = self._calc_price(data.get("Average"))
            self._min_tomorrow = self._calc_price(data.get("Min"))
            self._max_tomorrow = self._calc_price(data.get("Max"))
            self._off_peak_1_tomorrow = self._calc_price(
                data.get("Off-peak 1"))
            self._off_peak_2_tomorrow = self._calc_price(
                data.get("Off-peak 2"))
            self._peak_tomorrow = self._calc_price(data.get("Peak"))
            self._add_raw_calculated(True)
            # Reevaluate Today, when tomorrows prices are available
            self._add_raw_calculated(False)

        else:
            data = sorted(data.get("values"), key=itemgetter("start"))
            formatted_prices = [
                self._calc_price(
                    i.get("value"), fake_dt=dt_utils.as_local(i.get("start"))
                )
                for i in data
            ]

            if len(formatted_prices) and formatted_prices[0] is not None:
                offpeak1 = formatted_prices[0:8]
                peak = formatted_prices[9:17]
                offpeak2 = formatted_prices[20:]
                self._peak_tomorrow = mean(peak)
                self._off_peak_1_tomorrow = mean(offpeak1)
                self._off_peak_2_tomorrow = mean(offpeak2)
                self._average_tomorrow = mean(formatted_prices)
                self._min_tomorrow = min(formatted_prices)
                self._max_tomorrow = max(formatted_prices)
                self._add_raw_calculated(True)
                # Reevaluate Today, when tomorrows prices are available
                self._add_raw_calculated(False)

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
            sorted = self.get_sorted_prices_for_day(False)
            self._ten_cheapest_today = sorted[:10] if sorted else []
            self._five_cheapest_today = sorted[:5:] if sorted else []

    def _set_cheapest_hours_tomorrow(self):
        if self._data_tomorrow != None and len(self._data_tomorrow.get("values")):

            sorted = self.get_sorted_prices_for_day(True)

            self._ten_cheapest_tomorrow = sorted[:10] if sorted else []
            self._five_cheapest_tomorrow = sorted[:5] if sorted else []

    def _add_raw_calculated(self, is_tomorrow):
        if is_tomorrow and self.tomorrow_valid == False:
            return []

        data = self._data_tomorrow if is_tomorrow else self._data_today
        if data is None:
            _LOGGER.debug("No data available for %s, skipping calculation", "tomorrow" if is_tomorrow else "today")
            return
        data = sorted(data.get("values"), key=itemgetter("start"))

        result = []
        hour = 0
        percent_difference = (self.percent_difference + 100) / 100
        if is_tomorrow == False:
            difference = ((self._min / self._max) - 1)
            self._percent_threshold = ((difference / 4) * -1)
            # TODO, consider lowering thershold. for more micro-calculations. also other place?
            self._diff = self._max / max([self._min, 0.00001])
            self._set_cheapest_hours_today()

            self.small_price_difference_today = (
                self._diff < percent_difference)

        if self.tomorrow_valid == True and is_tomorrow == True:
            max_tomorrow = max([self._max_tomorrow, 0.00001])
            min_tomorrow = max([self._min_tomorrow, 0.00001])
            difference = ((min_tomorrow / max_tomorrow) - 1)
            self._percent_threshold_tomorrow = ((difference / 4) * -1)
            self._diff_tomorrow = max_tomorrow / min_tomorrow
            self._set_cheapest_hours_tomorrow()
            self.small_price_difference_tomorrow = (
                self._diff_tomorrow < percent_difference)

        data = self._format_time(data)
        peak = self._peak_tomorrow if is_tomorrow else self._peak
        max_price = self._max_tomorrow if is_tomorrow else self._max
        min_price = self._min_tomorrow if is_tomorrow else self._min
        average = self._average_tomorrow if is_tomorrow else self._average
        local_now = dt_utils.now()
        for res in data:

            price_now = float(self._calc_price(
                res["value"], fake_dt=res["start"]))
            is_max = price_now == max_price
            is_min = price_now == min_price
            is_low_price = price_now < average * self._low_price_cutoff
            is_over_peak = price_now > peak
            is_over_average = price_now > average

            next_hour = self.get_hour(hour+1, is_tomorrow)
            next_hour2 = self.get_hour(hour+2, is_tomorrow)
            next_hour3 = self.get_hour(hour+3, is_tomorrow)

            if next_hour != None and next_hour2 != None and next_hour3 != None:
                # TODO this will always be true when next day is not valid, so from 21.00 and onwards will not have price_next_hour.
                # should be better written.
                # this is fixed when next days prices are present though.
                price_next_hour3 = self._calc_price(
                    next_hour3["value"], fake_dt=next_hour3["start"]) or price_now
                price_next_hour2 = self._calc_price(
                    next_hour2["value"], fake_dt=next_hour2["start"]) or price_now
                price_next_hour = self._calc_price(
                    next_hour["value"], fake_dt=next_hour["start"]) or price_now
                is_gaining = self._is_gaining(hour, is_tomorrow)
                is_falling = self._is_falling(hour,is_tomorrow)
            else:
                is_gaining = None
                is_falling = None
                price_next_hour = None

            item = {
                "start": res["start"],
                "end": res["end"],
                "value": price_now,
                "price_next_hour": price_next_hour,
                "price_in_2_hours": price_next_hour2,
                "is_gaining": is_gaining,
                "is_falling": is_falling,
                'is_max': is_max,
                'is_min': is_min,
                'is_low_price': is_low_price,
                'is_over_peak': is_over_peak,
                'is_over_average': is_over_average,
            }

            is_five_most_expensive = self._is_five_most_expensive(
                item, is_tomorrow)
            item['price_percent_to_average'] = self.price_percent_to_average(
                item, is_tomorrow),
            item['is_ten_cheapest'] = self._is_ten_cheapest(item, is_tomorrow)
            item['is_five_cheapest'] = self._is_five_cheapest(
                item, is_tomorrow)
            item['is_five_most_expensive'] = is_five_most_expensive
            item['is_falling_a_lot_next_hour'] = self._is_falling_alot_next_hour(
                item)

            item['is_cheap_compared_to_future'] = self._is_in_five_cheapest_hours_in_the_future(item)
            # Todo, add this when complete.
            item['is_low_compared_to_tomorrow'] = self._is_low_compared_to_tomorrow(item)

            price_correction = self._get_temperature_correction(
                item, is_tomorrow)
            adjusted_price_correction = self._adjust_price_correction(
                price_correction, item)
            item["orginal_temperature_correction"] = price_correction
            item["temperature_correction"] = adjusted_price_correction
            item["reason"] = self._get_temperature_correction(
                item, is_tomorrow, True)

            # todo is a top?

            hour += 1
            # Check if current time falls within this period's time range
            if item["start"] <= local_now < item["end"]:
                self._current_period = item

            result.append(item)

        if is_tomorrow == False:
            self._today_calculated = result
        else:
            self._tomorrow_calculated = result


        self.update_sensors()

        return result

    def _is_ten_cheapest(self, item, is_tomorrow):
        ten_cheapest = self._ten_cheapest_tomorrow if is_tomorrow else self._ten_cheapest_today
        if ten_cheapest == None:
            return False

        if any(obj['start'] == item['start'] for obj in ten_cheapest):
            return True
        return False

    def _is_five_cheapest(self, item, is_tomorrow):
        five_cheapest = self._five_cheapest_tomorrow if is_tomorrow else self._five_cheapest_today
        if five_cheapest == None:
            return False

        if any(obj['start'] == item['start'] for obj in five_cheapest):
            return True
        return False

    def _is_in_five_cheapest_hours_in_the_future(self, item):
        future_five_cheapest = self._cheapest_hours_in_future_sorted[:5]
        now_in_five_future_cheapest = any(obj['start'] == item['start'] for obj in future_five_cheapest)
        today_date = dt_utils.now().date().strftime("%d")
        item_date = dt_utils.as_local(item['start']).strftime("%d")
        hour_is_today = today_date == item_date
        #todo add hour_is_today?
        return now_in_five_future_cheapest and self.tomorrow_valid

    def _is_low_compared_to_tomorrow(self, item):
        future_five = self._cheapest_hours_in_future_sorted[:5]
        if self.tomorrow_valid:
            #TODO NOT right. Price was lower for several hours later that day.
            item_in_five_future_cheapest = any(obj['start'] == item['start'] for obj in future_five)
            if item_in_five_future_cheapest:
                today_date = dt_utils.now().date().strftime("%d")
                item_date = dt_utils.as_local(item['start']).strftime("%d")
                hour_is_today = today_date == item_date
                if hour_is_today:
                    return True
        return False

    def _is_five_most_expensive(self, item, is_tomorrow):
        five_most_expensive = self._get_five_most_expensive_hours(is_tomorrow)
        if any(obj['start'] == item['start'] for obj in five_most_expensive):
            return True
        return False

    def get_prices_in_future_sorted(self, expensive_first=False):
        # todo, fix logic here.

        hours_today = self._data_today
        #    hours_tomorrow = self._data_tomorrow if len(self._data_tomorrow) else []
        # TypeError: object of type 'NoneType' has no len()

        hours_tomorrow = self._data_tomorrow
        today = hours_today.get("values")

        # todo: this check does not seem to work.
        if hours_tomorrow:
            tomorrow = hours_tomorrow.get("values")
            both = tomorrow + today
        else:
            both = today

        formatted_prices = [
            {
                'start': i.get('start'),
                'end': i.get('end'),
                'value': self._calc_price(
                    i.get("value"), fake_dt=dt_utils.as_local(i.get("start"))
                )
            }
            for i in both
        ]

        future_prices = []
        for hour in formatted_prices:
            if dt_utils.as_local(hour.get('start')) > (dt_utils.now() - timedelta(hours=1)):
                if not hour.get('value') == None :
                    future_prices.append(hour)
        if future_prices:
            return sorted(future_prices, key=itemgetter("value"), reverse=expensive_first)
        else:
            return []

    def get_sorted_prices_for_day(self, is_tomorrow, reverse=False):
        hours = self._data_tomorrow if is_tomorrow else self._data_today
        data = hours.get("values")
        formatted_prices = []
        if len(hours.get("values")):
            formatted_prices = [
                {
                    'start': i.get('start'),
                    'end': i.get('end'),
                    'value': self._calc_price(
                        i.get("value"), fake_dt=dt_utils.as_local(i.get("start"))
                    )
                }
                for i in data
            ]
        formatted_prices = sorted(
            formatted_prices, key=itemgetter("value"), reverse=reverse)
        return formatted_prices

    def _get_five_most_expensive_hours(self, is_tomorrow):
        sorted = self.get_sorted_prices_for_day(is_tomorrow, True)
        return sorted[:5] if sorted else []

    def update_sensors(self):
        async_dispatcher_send(self._hass, EVENT_CHECKED_STUFF)

    async def new_hr(self) -> None:
        _LOGGER.debug("New hour!, Tomorrow calculated is: %s",self._tomorrow_calculated)
        await self.check_stuff()


    async def new_day(self) -> None:
        await self.check_stuff()
        # New day, empty tomorrow if not yet done.
        if self._tomorrow_calculated != None:
            self._tomorrow_calculated = None
        # tomorrow_calculated is righly None here.
        _LOGGER.debug("New day!, Tomorrow calculated is: %s",self._tomorrow_calculated)

    async def _safe_api_call(self, api_method, *args, **kwargs):
        """Wrapper for API calls with error handling and logging"""
        try:
            result = await api_method(*args, **kwargs)
            if result:
                _LOGGER.debug("API call successful: %s", api_method.__name__)
                return result
            else:
                _LOGGER.debug("API call returned no data: %s", api_method.__name__)
                return None
        except Exception as e:
            _LOGGER.error("API call failed for %s: %s", api_method.__name__, str(e))
            return None

    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, asyncio.TimeoutError, OSError, Exception),
        max_tries=2,
        max_time=60,
        logger=_LOGGER,
        on_backoff=lambda details: _LOGGER.warning(
            "check_stuff API call failed, retrying in %s seconds (attempt %s/%s) for region %s: %s",
            details['wait'], details['tries'], details.get('max_tries', 'unknown'), 
            getattr(details.get('args', [None])[0], '_area', 'unknown'), details['exception']
        ),
        on_giveup=lambda details: _LOGGER.error(
            "check_stuff API call failed permanently after %s attempts over %s seconds for region %s: %s",
            details['tries'], details.get('elapsed', 'unknown'),
            getattr(details.get('args', [None])[0], '_area', 'unknown'), details['exception']
        ))
    async def check_stuff(self) -> None:
        """Cb to do some house keeping, called every hour to get the current hours price"""
        _LOGGER.debug("called check_stuff for region %s", self._area)
        start_time = dt_utils.now()
        if self._last_tick is None:
            self._last_tick = dt_utils.now()

        if self._data_tomorrow is None or len(self._data_tomorrow.get("values")) < 1:
            _LOGGER.debug(
                "PriceAnalyzerSensor _data_tomorrow is none, trying to fetch it")
            tomorrow = await self._safe_api_call(self.api.tomorrow, self._area, self._currency)
            if tomorrow:
                # _LOGGER.debug("PriceAnalyzerSensor FETCHED _data_tomorrow!, %s", tomorrow)
                self._data_tomorrow = tomorrow
                self._update_tomorrow(tomorrow)
            else:
                _LOGGER.debug(
                    "PriceAnalyzerSensor _data_tomorrow could not be fetched!")
                self._data_tomorrow = None
                self._tomorrow_calculated = None

        if self._data_today is None:
            _LOGGER.debug(
                "PriceAnalyzerSensor _data_today is none, trying to fetch it")
            today = await self._safe_api_call(self.api.today, self._area, self._currency)
            if today:
                self._data_today = today
                self._update(today)
            else:
                _LOGGER.debug(
                    "PriceAnalyzerSensor _data_today could not be fetched for %s!", self._area)

        # We can just check if this is the first hour.
        if is_new(self._last_tick, typ="day"):
            # if now.hour == 0:
            # No need to update if we got the info we need
            if self._data_tomorrow is not None:
                self._data_today = self._data_tomorrow
                self._today_calculated = self._tomorrow_calculated
                self._average = self._average_tomorrow
                self._max = self._max_tomorrow
                self._min = self._min_tomorrow
                self._off_peak_1 = self._off_peak_1_tomorrow
                self._off_peak_2 = self._off_peak_2_tomorrow
                self._peak = self._peak_tomorrow
                self._percent_threshold = self._percent_threshold_tomorrow
                self._diff = self._diff_tomorrow
                self._ten_cheapest_today = self._ten_cheapest_tomorrow
                self._five_cheapest_today = self._five_cheapest_tomorrow

                self._update(self._data_today)
                self._data_tomorrow = None
                self._tomorrow_calculated = None
            else:
                today = await self._safe_api_call(self.api.today, self._area, self._currency)
                if today:
                    self._data_today = today
                    self._update(today)


        if self._data_today:
            self._cheapest_hours_in_future_sorted = self.get_prices_in_future_sorted()

        # Updates the current for this hour.
        await self._update_current_price()

        # Update current_period to reflect the current time
        self._update_current_period()

        # try to force tomorrow.
        tomorrow = await self._safe_api_call(self.api.tomorrow, self._area, self._currency)
        if tomorrow:
            # often inf..
            _LOGGER.debug(
                "PriceAnalyzerSensor force FETCHED _data_tomorrow!")
            self._data_tomorrow = tomorrow
            self._update_tomorrow(tomorrow)

        self._last_tick = dt_utils.now()
        self.update_sensors()
        
        # Log completion time for performance monitoring
        elapsed = (dt_utils.now() - start_time).total_seconds()
        if elapsed > 5:  # Log if it took more than 5 seconds
            _LOGGER.warning("check_stuff completed for region %s in %s seconds (slow performance)", 
                          self._area, elapsed)
        else:
            _LOGGER.debug("check_stuff completed for region %s in %s seconds", self._area, elapsed)
        # Removed recursive calls to check_stuff() to prevent infinite loops
        # These conditions will be handled in the next scheduled check