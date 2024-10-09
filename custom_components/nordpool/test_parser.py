import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from operator import itemgetter

import aiohttp
from aiozoneinfo import async_get_time_zone
# https://repl.it/repls/WildImpishMass
from dateutil import tz
from dateutil.parser import parse as parse_dt
from nordpool.base import CurrencyMismatch
from nordpool.elspot import Prices

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


INVALID_VALUES = frozenset((None, float("inf")))


class InvalidValueException(ValueError):
    pass



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

        resp = await self.client.get(url, params=kwargs, headers={
            'Origin': 'https://data.nordpoolgroup.com'
        })
        _LOGGER.debug("requested %s %s", resp.url, kwargs)

        return await resp.json()

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

        # If areas isn't a list, make it one
        if areas is None:
            areas = []
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
        if areas is None:
            areas = []
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
        raw = [await self._async_parse_json(i, areas) for i in res]

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
        """Helper to fe
tch yearly data, see Prices.fetch()"""
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
















tzs = {
    "DK1": "Europe/Copenhagen",
    "DK2": "Europe/Copenhagen",
    "FI": "Europe/Helsinki",
    "EE": "Europe/Tallinn",
    "LT": "Europe/Vilnius",
    "LV": "Europe/Riga",
    "Oslo": "Europe/Oslo",
    "Kr.sand": "Europe/Oslo",
    "Bergen": "Europe/Oslo",
    "Molde": "Europe/Oslo",
    "Tr.heim": "Europe/Oslo",
    "Tromsø": "Europe/Oslo",
    "SE1": "Europe/Stockholm",
    "SE2": "Europe/Stockholm",
    "SE3": "Europe/Stockholm",
    "SE4": "Europe/Stockholm",
    # What zone is this?
    "SYS": "Europe/Stockholm",
    "FR": "Europe/Paris",
    "BE": "Europe/Brussels",
    "AT": "Europe/Vienna",
    "DE-LU": "Europe/Berlin"
}


def add_junk(d):
    # move this
    for key in ["Average", "Min", "Max", "Off-peak 1", "Off-peak 2", "Peak"]:
        d[key] = float("inf")

    return d


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
                zone = await async_get_time_zone(zone)

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
                if start_of_day <= local and local <= end_of_day:
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




if __name__ == "__main__":
    import asyncclick as click

    @click.command()
    @click.option('--region', '-r', default="Kr.sand")
    @click.option('--currency', '-c', default="NOK")
    @click.option('--vat', '-v', default=0)
    async def manual_check(region, currency, vat):


        ts = tz.gettz(tzs[region])
        utc = datetime.utcnow()

        # Convert time zone
        lt = utc.astimezone(ts)
        dt_today = lt
        dt_yesterday = lt + timedelta(days=-1)

        spot = AioPrices(currency, aiohttp.client.ClientSession())
        yesterday = await spot.hourly(end_date=dt_yesterday, areas=[region])
        today = await spot.hourly(end_date=dt_today, areas=[region])
        tomorrow = await spot.hourly(end_date=dt_today + timedelta(days=1), areas=[region])
        #print(today)
        #print(pprint(today.get("areas")))
        #return

        results = [yesterday, today, tomorrow]

        rsults = await join_result_for_correct_time(results, dt_today)

        values = []
        for key, value in rsults["areas"].items():
            values = []
            if key == region or region is None:
                for v in rsults["areas"][key]["values"]:
                    zone = tzs.get(key)
                    if zone is None:
                        continue
                    zone = tz.gettz(zone)

                    i = {
                        "value": v["value"],
                        "start": v["start"].astimezone(zone),
                        "end": v["end"].astimezone(zone),
                    }
                    values.append(i)

            if len(values):
                print("Report for region %s" % key)
            for vvv in sorted(values, key=itemgetter("start")):
                print("from %s to %s price %s" % (vvv["start"], vvv["end"], vvv["value"]))
            if len(values):
                print("total hours %s" % len(values))

    asyncio.run(manual_check())
