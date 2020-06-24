import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta

from dateutil import tz
from dateutil.parser import parse as parse_dt
from nordpool.elspot import Prices

from .misc import add_junk

_LOGGER = logging.getLogger(__name__)


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
}


def join_result_for_correct_time(results, dt):
    """Parse a list of responses from the api
       to extract the correct hours in there timezone.
    """
    #utc = datetime.utcnow()
    fin = defaultdict(dict)
    _LOGGER.debug("join_result_for_correct_time %s", dt)
    utc = dt

    for day_ in results:
        for key, value in day_.get("areas", {}).items():
            zone = tzs.get(key)
            if zone is None:
                _LOGGER.debug("Skipping %s", key)
                continue
            else:
                zone = tz.gettz(zone)

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
                hour=23, minute=59, second=59, microsecond=9999
            )

            for val in values:
                local = val["start"].astimezone(zone)
                if start_of_day <= local and local <= end_of_day:
                    fin["areas"][key]["values"].append(val)

    return fin


class AioPrices(Prices):
    def __init__(self, currency, client, tz=None):
        super().__init__(currency)
        self.client = client
        self.tz = tz

        #if self.tz is None:
        #    self.tz = tz.gettz("Europe/Stockholm")

    async def _io(self, url, **kwargs):

        resp = await self.client.get(url, params=kwargs)
        _LOGGER.debug("requested %s %s", resp.url, kwargs)

        return await resp.json()

    async def _fetch_json(self, data_type, end_date=None):
        """ Fetch JSON from API """
        # If end_date isn't set, default to tomorrow
        if end_date is None:
            end_date = date.today() + timedelta(days=1)
        # If end_date isn't a date or datetime object, try to parse a string
        if not isinstance(end_date, date) and not isinstance(end_date, datetime):
            end_date = parse_dt(end_date)

        return await self._io(
            self.API_URL % data_type,
            currency=self.currency,
            endDate=end_date.strftime("%d-%m-%Y"),
        )

    async def fetch(self, data_type, end_date=None, areas=[]):
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

        # Check how to handle all time zone in this,
        # dunno how to do this yet.
        #stock = datetime.utcnow().astimezone(tz.gettz("Europe/Stockholm"))
        #stock_offset = stock.utcoffset().total_seconds()
        # compare utc offset
        if self.tz == tz.gettz("Europe/Stockholm"):
            data = await self._fetch_json(data_type, end_date)
            return self._parse_json(data, areas)
        else:

            yesterday = datetime.now() - timedelta(days=1)
            today = datetime.now()
            tomorrow = datetime.now() + timedelta(days=1)

            jobs = [
                self._fetch_json(data_type, yesterday),
                self._fetch_json(data_type, today),
                self._fetch_json(data_type, tomorrow),
            ]

            res = await asyncio.gather(*jobs)
            raw = [self._parse_json(i, areas) for i in res]
            return join_result_for_correct_time(raw, end_date)

    async def hourly(self, end_date=None, areas=[]):
        """ Helper to fetch hourly data, see Prices.fetch() """
        return await self.fetch(self.HOURLY, end_date, areas)

    async def daily(self, end_date=None, areas=[]):
        """ Helper to fetch daily data, see Prices.fetch() """
        return await self.fetch(self.DAILY, end_date, areas)

    async def weekly(self, end_date=None, areas=[]):
        """ Helper to fetch weekly data, see Prices.fetch() """
        return await self.fetch(self.WEEKLY, end_date, areas)

    async def monthly(self, end_date=None, areas=[]):
        """ Helper to fetch monthly data, see Prices.fetch() """
        return await self.fetch(self.MONTHLY, end_date, areas)

    async def yearly(self, end_date=None, areas=[]):
        """ Helper to fetch yearly data, see Prices.fetch() """
        return await self.fetch(self.YEARLY, end_date, areas)

    def _conv_to_float(self, s):
        """ Convert numbers to float. Return infinity, if conversion fails. """
        try:
            return float(s.replace(',', '.').replace(" ", ""))
        except ValueError:
            return float('inf')
