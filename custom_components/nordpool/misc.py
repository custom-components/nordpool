import logging

from collections import defaultdict
from statistics import mean

import pendulum

__all__ = ["is_new", "has_junk", "extract_attrs"]

_LOGGER = logging.getLogger(__name__)


def is_new(date=None, typ="day") -> bool:
    """Utility to check if its a new hour or day."""
    current = pendulum.now()
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
    tzn = pendulum.now().timezone_name
    for item in data:
        curr = pendulum.instance(item.get("start")).in_timezone(tzn)
        peak = pendulum.period(curr.at(8), curr.at(19).end_of("hour"))
        offpeek1 = pendulum.period(curr.start_of("day"), curr.at(8))
        offpeek2 = pendulum.period(curr.at(20), curr.at(23).end_of("hour"))

        if curr in peak:
            d["peak"].append(item.get("value"))
        elif curr in offpeek1:
            d["offpeek1"].append(item.get("value"))
        elif curr in offpeek2:
            d["offpeek2"].append(item.get("value"))

        items.append(item.get("value"))

    d["Peak"] = mean(d["peak"])
    d["Off-peak 1"] = mean(d["offpeek1"])
    d["Off-peak 2"] = mean(d["offpeek2"])
    d["Average"] = mean(items)
    d["Min"] = min(items)
    d["Max"] = max(items)

    return dict(d)
