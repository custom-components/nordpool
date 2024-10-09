import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta

import aiohttp
import backoff
from dateutil.parser import parse as parse_dt
from homeassistant.util import dt as dt_utils
from nordpool.base import CurrencyMismatch
from nordpool.elspot import Prices
from pytz import timezone, utc

from .misc import add_junk

_LOGGER = logging.getLogger(__name__)

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


class InvalidValueException(ValueError):
    pass


async def join_result_for_correct_time(results, dt):
    """Parse a list of responses from the api
    to extract the correct hours in there timezone.
    """
    # utc = datetime.utcnow()
    fin = defaultdict(dict)
    # _LOGGER.debug("join_result_for_correct_time %s", dt)
    utc = dt

    for day_ in results:
        for key, value in day_.get("areas", {}).items():
            zone = tzs.get(key)
            if zone is None:
                _LOGGER.debug("Skipping %s", key)
                continue
            else:
                zone = await dt_utils.async_get_time_zone(zone)

            # We add junk here as the peak etc
            # from the api is based on cet, not the
            # hours in the we want so invalidate them
            # its later corrected in the sensor.
            value = add_junk(value)

            values = day_["areas"][key].pop("values")

            # We need to check this so we dont overwrite stuff.
            if key not in fin["areas"]:
                fin["areas"][key] = {}
            fin["areas"][key].update(value)
            if "values" not in fin["areas"][key]:
                fin["areas"][key]["values"] = []

            start_of_day = utc.astimezone(zone).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end_of_day = utc.astimezone(zone).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )

            for val in values:
                local = val["start"].astimezone(zone)
                local_end = val["end"].astimezone(zone)
                if start_of_day <= local <= end_of_day:
                    if local == local_end:
                        _LOGGER.info(
                            "Hour has the same start and end, most likly due to dst change %s exluded this hour",
                            val,
                        )
                    elif val['value'] in INVALID_VALUES:
                        raise InvalidValueException(f"Invalid value in {val} for area '{key}'")
                    else:
                        fin["areas"][key]["values"].append(val)

    return fin


class AioPrices(Prices):
    """Interface"""

    def __init__(self, currency, client, timeezone=None):
        super().__init__(currency)
        self.client = client
        self.timeezone = timeezone
        (self.HOURLY, self.DAILY, self.WEEKLY, self.MONTHLY, self.YEARLY) = ("DayAheadPrices", "AggregatePrices",
                                                                             "AggregatePrices", "AggregatePrices",
                                                                             "AggregatePrices")
        self.API_URL = "https://dataportal-api.nordpoolgroup.com/api/%s"

    async def _io(self, url, **kwargs):

        resp = await self.client.get(url, params=kwargs)
        _LOGGER.debug("requested %s %s", resp.url, kwargs)

        if resp.status == 204:
            return None

        return await resp.json()

    def _parse_dt(self, time_str):
        ''' Parse datetimes to UTC from Stockholm time, which Nord Pool uses. '''
        time = parse_dt(time_str, tzinfos={"Z": timezone("Europe/Stockholm")})
        if time.tzinfo is None:
            return timezone('Europe/Stockholm').localize(time).astimezone(utc)
        return time.astimezone(utc)

    def _parse_json(self, data, areas=None):
        """
        Parse json response from fetcher.
        Returns dictionary with
            - start time
            - end time
            - update time
            - currency
            - dictionary of areas, based on selection
                - list of values (dictionary with start and endtime and value)
                - possible other values, such as min, max, average for hourly
        """

        if areas is None:
            areas = []
        # If areas isn't a list, make it one

        if not isinstance(areas, list):
            areas = list(areas)

        if data.get("status", 200) != 200 and "version" not in data:
            raise Exception(f"Invalid response from Nordpool API: {data}")

        # Update currency from data
        currency = data['currency']

        # Ensure that the provided currency match the requested one
        if currency != self.currency:
            raise CurrencyMismatch

        start_time = None
        end_time = None

        if len(data['multiAreaEntries']) > 0:
            start_time = self._parse_dt(data['multiAreaEntries'][0]['deliveryStart'])
            end_time = self._parse_dt(data['multiAreaEntries'][-1]['deliveryEnd'])
        updated = self._parse_dt(data['updatedAt'])

        area_data = {}

        # Loop through response rows
        for r in data['multiAreaEntries']:
            row_start_time = self._parse_dt(r['deliveryStart'])
            row_end_time = self._parse_dt(r['deliveryEnd'])

            # Loop through columns
            for area_key in r['entryPerArea'].keys():
                area_price = r['entryPerArea'][area_key]
                # If areas is defined and name isn't in areas, skip column
                if area_key not in areas:
                    continue

                # If name isn't in area_data, initialize dictionary
                if area_key not in area_data:
                    area_data[area_key] = {
                        'values': [],
                    }

                # Append dictionary to value list
                area_data[area_key]['values'].append({
                    'start': row_start_time,
                    'end': row_end_time,
                    'value': self._conv_to_float(area_price),
                })

        return {
            'start': start_time,
            'end': end_time,
            'updated': updated,
            'currency': currency,
            'areas': area_data
        }

    async def _fetch_json(self, data_type, end_date=None, areas=None):
        """Fetch JSON from API"""
        # If end_date isn't set, default to tomorrow
        if areas is None or len(areas) == 0:
            raise Exception("Cannot query with empty areas")
        if end_date is None:
            end_date = date.today() + timedelta(days=1)
        # If end_date isn't a date or datetime object, try to parse a string
        if not isinstance(end_date, date) and not isinstance(end_date, datetime):
            end_date = parse_dt(end_date)



        return await self._io(
            self.API_URL % data_type,
            currency=self.currency,
            market="DayAhead",
            deliveryArea=",".join(areas),
            date=end_date.strftime("%Y-%m-%d"),
        )

    # Add more exceptions as we find them. KeyError is raised when the api return
    # junk due to currency not being available in the data.
    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, KeyError),
        logger=_LOGGER, max_value=20)
    async def fetch(self, data_type, end_date=None, areas=None):
        """
        Fetch data from API.
        Inputs:
            - data_type
                API page id, one of Prices.HOURLY, Prices.DAILY etc
            - end_date
                datetime to end the data fetching
                defaults to tomorrow
            - areas
                list of areas to fetch, such as ['SE1', 'SE2', 'FI']
                defaults to all areas
        Returns dictionary with
            - start time
            - end time
            - update time
            - currency
            - dictionary of areas, based on selection
                - list of values (dictionary with start and endtime and value)
                - possible other values, such as min, max, average for hourly
        """
        if areas is None:
            areas = []

        yesterday = datetime.now() - timedelta(days=1)
        today = datetime.now()
        tomorrow = datetime.now() + timedelta(days=1)

        jobs = [
            self._fetch_json(data_type, yesterday, areas),
            self._fetch_json(data_type, today, areas),
            self._fetch_json(data_type, tomorrow, areas),
        ]

        res = await asyncio.gather(*jobs)
        raw = [await self._async_parse_json(i, areas) for i in res if i]

        return await join_result_for_correct_time(raw, end_date)

    async def _async_parse_json(self, data, areas):
        """
        Async version of _parse_json to prevent blocking calls inside the event loop.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._parse_json, data, areas)

    async def hourly(self, end_date=None, areas=None):
        """Helper to fetch hourly data, see Prices.fetch()"""
        if areas is None:
            areas = []
        return await self.fetch(self.HOURLY, end_date, areas)

    async def daily(self, end_date=None, areas=None):
        """Helper to fetch daily data, see Prices.fetch()"""
        if areas is None:
            areas = []
        return await self.fetch(self.DAILY, end_date, areas)

    async def weekly(self, end_date=None, areas=None):
        """Helper to fetch weekly data, see Prices.fetch()"""
        if areas is None:
            areas = []
        return await self.fetch(self.WEEKLY, end_date, areas)

    async def monthly(self, end_date=None, areas=None):
        """Helper to fetch monthly data, see Prices.fetch()"""
        if areas is None:
            areas = []
        return await self.fetch(self.MONTHLY, end_date, areas)

    async def yearly(self, end_date=None, areas=None):
        """Helper to fetch yearly data, see Prices.fetch()"""
        if areas is None:
            areas = []
        return await self.fetch(self.YEARLY, end_date, areas)

    def _conv_to_float(self, s):
        """Convert numbers to float. Return infinity, if conversion fails."""
        # Skip if already float
        if isinstance(s, float):
            return s
        try:
            return float(s.replace(",", ".").replace(" ", ""))
        except ValueError:
            return float("inf")
