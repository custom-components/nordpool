from datetime import datetime, timedelta
from typing import Any, Optional
from collections.abc import Awaitable, Callable

#
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback, HassJob
from homeassistant.loader import bind_hass
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import (
    async_track_time_interval,
    async_track_point_in_utc_time,
)
from pytz import timezone

# For targeted patching in tests
time_tracker_utcnow = dt_util.utcnow


__ALL__ = ["stock", "async_track_time_change_in_tz"]


def stock(d):
    """convert datetime to stocholm time."""
    return d.astimezone(timezone("Europe/Stockholm"))


@callback
@bind_hass
def async_track_utc_time_change(
    hass: HomeAssistant,
    action: None,
    hour: Optional[Any] = None,
    minute: Optional[Any] = None,
    second: Optional[Any] = None,
    tz: Optional[Any] = None,
) -> CALLBACK_TYPE:
    """Add a listener that will fire if time matches a pattern."""
    # This is function is modifies to support timezones.

    # We do not have to wrap the function with time pattern matching logic
    # if no pattern given
    if all(val is None for val in (hour, minute, second)):
        # Previously this relied on EVENT_TIME_FIRED
        # which meant it would not fire right away because
        # the caller would always be misaligned with the call
        # time vs the fire time by < 1s. To preserve this
        # misalignment we use async_track_time_interval here
        return async_track_time_interval(hass, action, timedelta(seconds=1))

    job = HassJob(action)
    matching_seconds = dt_util.parse_time_expression(second, 0, 59)
    matching_minutes = dt_util.parse_time_expression(minute, 0, 59)
    matching_hours = dt_util.parse_time_expression(hour, 0, 23)

    def calculate_next(now: datetime) -> datetime:
        """Calculate and set the next time the trigger should fire."""
        ts_now = now.astimezone(tz) if tz else now
        return dt_util.find_next_time_expression_time(
            ts_now, matching_seconds, matching_minutes, matching_hours
        )

    time_listener: CALLBACK_TYPE | None = None

    @callback
    def pattern_time_change_listener(_: datetime) -> None:
        """Listen for matching time_changed events."""
        nonlocal time_listener

        now = time_tracker_utcnow()
        hass.async_run_hass_job(job, now.astimezone(tz) if tz else now)

        time_listener = async_track_point_in_utc_time(
            hass,
            pattern_time_change_listener,
            calculate_next(now + timedelta(seconds=1)),
        )

    time_listener = async_track_point_in_utc_time(
        hass, pattern_time_change_listener, calculate_next(dt_util.utcnow())
    )

    @callback
    def unsub_pattern_time_change_listener() -> None:
        """Cancel the time listener."""
        assert time_listener is not None
        time_listener()

    return unsub_pattern_time_change_listener


@callback
@bind_hass
def async_track_time_change_in_tz(
    hass: HomeAssistant,
    action: None,
    # action: Callable[[datetime], Awaitable[None] | None],
    hour: Optional[Any] = None,
    minute: Optional[Any] = None,
    second: Optional[Any] = None,
    tz: Optional[Any] = None,
) -> CALLBACK_TYPE:
    """Add a listener that will fire if UTC time matches a pattern."""
    return async_track_utc_time_change(hass, action, hour, minute, second, tz)
