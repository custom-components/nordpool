import logging
import sys  # Make sure plexapi is in the systempath
from collections import defaultdict
from datetime import date, datetime, timedelta
from operator import itemgetter
from os.path import abspath, dirname
from pprint import pprint

import requests
# https://repl.it/repls/WildImpishMass
from dateutil import tz
from dateutil.parser import parse as parse_dt
from nordpool import elspot


class PP(elspot.Prices):
    def __init__(self, currency):
        super().__init__(currency)
        self.API_URL_CURRENCY = "https://www.nordpoolgroup.com/api/marketdata/page/%s"

    def _fetch_json(self, data_type, end_date=None):
        ''' Fetch JSON from API '''
        # If end_date isn't set, default to tomorrow
        if end_date is None:
            end_date = date.today() + timedelta(days=1)
        # If end_date isn't a date or datetime object, try to parse a string
        if not isinstance(end_date, date) and not isinstance(end_date, datetime):
            end_date = parse_dt(end_date)

        if self.currency != "EUR":
            data_type = 23

        # Create request to API
        r = requests.get(self.API_URL % data_type, params={
            'currency': self.currency,
            'endDate': end_date.strftime('%d-%m-%Y'),
        })
        # Return JSON response
        return r.json()














_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


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


def join_result_for_correct_time(results):
    """Parse a list of responses from the api
       to extract the correct hours in there timezone.


    """
    utc = datetime.utcnow()
    fin = defaultdict(dict)

    n = 0
    for day_ in results:
        n += 1
        print(n)
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
                    #
                    if n == 1:
                        # this is yesterday
                        print("outlier %s %s %s %s" % (key, val["start"], val["end"], val["value"]))
                    fin["areas"][key]["values"].append(val)

    return fin




if __name__ == "__main__":
    import click

    @click.command()
    @click.option('--region', '-r', default="Kr.sand")
    @click.option('--currency', '-c', default="NOK")
    @click.option('--vat', '-v', default=0)
    def manual_check(region, currency, vat):


        ts = tz.gettz(tzs[region])
        utc = datetime.utcnow()

        # Convert time zone
        lt = utc.astimezone(ts)
        dt_today = lt.date()
        dt_yesterday = lt + timedelta(days=-1)

        spot = PP(currency)
        yesterday = spot.hourly(end_date=dt_yesterday)
        today = spot.hourly(end_date=dt_today)
        tomorrow = spot.hourly(end_date=dt_today + timedelta(days=1))
        #print(today)
        print(pprint(today.get("areas")))
        return

        results = [yesterday, today, tomorrow]

        data = join_result_for_correct_time(results)
        values = []
        for key, value in data["areas"].items():
            values = []
            if key == region or region is None:
                for v in data["areas"][key]["values"]:
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

    manual_check()
