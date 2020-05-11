import logging
from collections import defaultdict
from datetime import datetime, timedelta
from operator import itemgetter

# https://repl.it/repls/WildImpishMass
from dateutil import tz
from nordpool import elspot

_LOGGER = logging.getLogger(__name__)

to_helsinki = tz.gettz("Europe/Helsinki")
utc = datetime.utcnow()

# Convert time zone
hel = utc.astimezone(to_helsinki)
dt_today = hel.date()
dt_yesterday = hel + timedelta(days=-1)
print("Requsting data for %s - %s" % (dt_yesterday.date(), dt_today))

spot = elspot.Prices("EUR")
yesterday = spot.hourly(end_date=dt_yesterday)
today = spot.hourly(end_date=dt_today)


results = [yesterday, today]

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
                hour=23, minute=59, second=59, microsecond=9999
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


def manual_check(data, region="FI"):
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


res = join_result_for_correct_time([yesterday, today])
manual_check(res, region="FI")
