import logging
from collections import defaultdict
from statistics import mean

from homeassistant.util import dt as dt_utils
from pytz import timezone

# import pendulum

__all__ = ["is_new", "has_junk", "extract_attrs", "start_of", "end_of", "stock"]

_LOGGER = logging.getLogger(__name__)


def stock(d):
    """convert datetime to stocholm time."""
    return d.astimezone(timezone("Europe/Stockholm"))


def start_of(d, typ_="hour"):
    if typ_ == "hour":
        return d.replace(minute=0, second=0, microsecond=0)
    elif typ_ == "day":
        return d.replace(hour=0, minute=0, microsecond=0)


def time_in_range(start, end, x):
    """Return true if x is in the range [start, end]"""
    if start <= end:
        return start <= x <= end
    else:
        return start <= x or x <= end


def end_of(d, typ_="hour"):
    if typ_ == "hour":
        return d.replace(minute=59, second=59, microsecond=999999)
    elif typ_ == "day":
        return d.replace(hour=23, minute=59, second=59, microsecond=999999)


def is_new(date=None, typ="day") -> bool:
    """Utility to check if its a new hour or day."""
    # current = pendulum.now()
    current = dt_utils.now()
    if typ == "day":
        if date.date() != current.date():
            _LOGGER.debug("Its a new day!")
            return True
        return False

    elif typ == "hour":
        if current.hour != date.hour:
            _LOGGER.debug("Its a new hour!")
            return True
        return False


def is_inf(d):
    if d == float("inf"):
        return True
    return False


def has_junk(data) -> bool:
    """Check if data has some infinity values.

    Args:
        data (dict): Holds the data from the api.

    Returns:
        TYPE: True if there is any infinity values else False
    """
    cp = dict(data)
    cp.pop("values", None)
    if any(map(is_inf, cp.values())):
        return True
    return False


def extract_attrs(data) -> dict:
    """
    Peak = 08:00 to 20:00
    Off peak 1 = 00:00 to 08:00
    off peak 2 = 20:00 to 00:00
    """
    items = []
    d = defaultdict(list)

    peak_start = start_of(dt_utils.now().replace(hour=8), "hour")
    peak_end = end_of(dt_utils.now().replace(hour=19), "hour")
    offpeek1_start = dt_utils.start_of_local_day()
    offpeek1_end = end_of(offpeek1_start.replace(hour=7), "hour")
    offpeek2_start = start_of(dt_utils.now().replace(hour=8), "hour")
    offpeek2_end = end_of(dt_utils.now().replace(hour=23), "hour")

    for item in data:
        curr = dt_utils.as_local(item.get("start"))

        if time_in_range(peak_start, peak_end, curr):
            d["peak"].append(item.get("value"))

        elif time_in_range(offpeek1_start, offpeek1_end, curr):
            d["offpeek1"].append(item.get("value"))

        elif time_in_range(offpeek2_start, offpeek2_end, curr):
            d["offpeek2"].append(item.get("value"))

        items.append(item.get("value"))

    d["Peak"] = mean(d["peak"])
    d["Off-peak 1"] = mean(d["offpeek1"])
    d["Off-peak 2"] = mean(d["offpeek2"])
    d["Average"] = mean(items)
    d["Min"] = min(items)
    d["Max"] = max(items)

    return dict(d)
