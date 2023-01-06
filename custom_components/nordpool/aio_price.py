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
    "FR": "Europe/Paris",
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "AT": "Europe/Vienna",
    "DE-LU": "Europe/Berlin",
}


# List of page index for hourly data
# Some is disable as the don't contain the other currencies NOK etc
# or there are som issues with data paring for some one the, DataStartdate
# Lets comeback and fix that later, just need to adjust the self._parser.
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


def join_result_for_correct_time(results, dt):
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
                hour=23, minute=59, second=59, microsecond=999999
            )

            for val in values:
                local = val["start"].astimezone(zone)
                if start_of_day <= local and local <= end_of_day:
                    fin["areas"][key]["values"].append(val)

    # _LOGGER.debug("Combines result: %s", fin)

    return fin


class AioPrices(Prices):
    """Interface"""

    def __init__(self, currency, client, timeezone=None):
        super().__init__(currency)
        self.client = client
        self.timeezone = timeezone
        self.API_URL_CURRENCY = "https://www.nordpoolgroup.com/api/marketdata/page/%s"

    async def _io(self, url, **kwargs):

        resp = await self.client.get(url, params=kwargs)
        _LOGGER.debug("requested %s %s", resp.url, kwargs)

        return await resp.json()

    async def _fetch_json(self, data_type, end_date=None, areas=None):
        """Fetch JSON from API"""
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

        # now = datetime.utcnow()
        # timezone_for_data = now.astimezone(tz.gettz(ts))
        # stock = datetime.utcnow().astimezone(tz.gettz("Europe/Stockholm"))
        # if stock.utcoffset(now) == timezone_for_data.utcoffset(now):
        #    pass

        # compare utc offset
        if self.timeezone == tz.gettz("Europe/Stockholm"):
            data = await self._fetch_json(data_type, end_date, areas)
            return self._parse_json(data, areas)
        else:
            yesterday = datetime.now() - timedelta(days=1)
            today = datetime.now()
            tomorrow = datetime.now() + timedelta(days=1)

            # days = [yesterday, today, tomorrow]
            # Workaround for api changes.
            # Disabled for now as nordpool have fixed the api endpoint that we used.
            # if self.currency != "EUR":
            #    # Only need to check for today price
            #    # as this is only available for dk, nor, se
            #    # and all of them is in the corrent timezone.
            #    days = [today, tomorrow]
            #    idx_list = COUNTRY_BASE_PAGE.values()
            #    stuff = []
            #    for d in days:
            #        dat = {"areas": {}}
            #        for pageidx in idx_list:
            #            task = self._io(
            #                self.API_URL_CURRENCY % pageidx,
            #                currency=self.currency,
            #                endDate=d.strftime("%d-%m-%Y"),
            #            )
            #            data = await task
            #
            #            try:
            #                jd = self._parse_json(data, areas)
            #
            #               for key, value in jd.get("areas").items():
            #                    dat["areas"][key] = value
            #
            #            except Exception as e:
            #                _LOGGER.debug("Error with %s %s", d, pageidx)
            #                raise
            #
            #        stuff.append(dat)
            #
            #    return join_result_for_correct_time(stuff, end_date)

            # else:

            jobs = [
                self._fetch_json(data_type, yesterday),
                self._fetch_json(data_type, today),
                self._fetch_json(data_type, tomorrow),
            ]

            res = await asyncio.gather(*jobs)

            raw = [self._parse_json(i, areas) for i in res]
            return join_result_for_correct_time(raw, end_date)

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
        try:
            return float(s.replace(",", ".").replace(" ", ""))
        except ValueError:
            return float("inf")
