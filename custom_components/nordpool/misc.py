import logging
from collections import defaultdict
from operator import itemgetter, not_
from statistics import mean
from typing import Union
from datetime import datetime

import pytz
from homeassistant.util import dt as dt_util
from pytz import timezone

UTC = pytz.utc

__all__ = [
    "is_new",
    "has_junk",
    "extract_attrs",
    "start_of",
    "end_of",
    "stock",
    "add_junk",
    "test_valid_nordpooldata",
    "predicate",
]


_LOGGER = logging.getLogger(__name__)


def predicate(value: Union[bool, None]) -> bool:
    """Helper to stop the retry on None values."""
    # _LOGGER.debug("Should retry %s", bool(value))
    if value is None:
        _LOGGER.debug("No data is available yet. Stopping retries")
        return False
    return not_(value)


def add_junk(data: dict) -> dict:
    """Used to add inf values to a dict"""
    for key in ["Average", "Min", "Max", "Off-peak 1", "Off-peak 2", "Peak"]:
        data[key] = float("inf")

    return data


def stock(d: datetime):
    """convert datetime to stockholm time."""
    return d.astimezone(timezone("Europe/Stockholm"))


def start_of(d: datetime, typ_: str = "hour") -> datetime:
    """Change a datetime object to start of day or hour"""
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


def end_of(d: datetime, typ_: str = "hour") -> datetime:
    """Change a datetime object to end of hour or day"""
    if typ_ == "hour":
        return d.replace(minute=59, second=59, microsecond=999999)
    elif typ_ == "day":
        return d.replace(hour=23, minute=59, second=59, microsecond=999999)


def is_new(date=None, typ="day") -> bool:
    """Utility to check if its a new hour or day."""
    # current = pendulum.now()
    current = dt_util.now()
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


def is_inf(value) -> bool:
    if value == float("inf"):
        return True
    return False


def test_valid_nordpooldata(data_, region=None):
    """Checks that the data is OK."""
    # _LOGGER.debug("Checking for inf value in data for %s", region)

    if data_ is None:
        return False

    # _LOGGER.debug("DATA %s", pformat(data_))
    if isinstance(data_, dict):
        data_ = [data_]

    for data in data_:
        for _, v in data.items():
            for area, real_data in v.items():
                # _LOGGER.debug("area %s", area)
                if region is None or area in region:
                    if any(
                        i["value"] == float("inf") for i in real_data.get("values", {})
                    ):
                        _LOGGER.debug("Found infinty invalid data in area %s", area)
                        return False

    return True


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
    """Extrace the correct attrs from a dict"""
    d = defaultdict(list)
    items = [i.get("value") for i in data]

    if len(data):
        data = sorted(data, key=itemgetter("start"))
        offpeak1 = [i.get("value") for i in data[0:8]]
        peak = [i.get("value") for i in data[9:17]]
        offpeak2 = [i.get("value") for i in data[20:]]

        d["Peak"] = mean(peak)
        d["Off-peak 1"] = mean(offpeak1)
        d["Off-peak 2"] = mean(offpeak2)
        d["Average"] = mean(items)
        d["Min"] = min(items)
        d["Max"] = max(items)

        return d

    return data
