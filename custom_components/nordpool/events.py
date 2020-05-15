from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from homeassistant.const import ATTR_NOW, EVENT_TIME_CHANGED
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.loader import bind_hass
from homeassistant.util import dt as dt_util
from pytz import timezone


def stock(d):
    """convert datetime to stocholm time."""
    return d.astimezone(timezone("Europe/Stockholm"))


@callback
@bind_hass
def async_track_utc_time_change(
    hass: HomeAssistant,
    action: Callable[..., None],
    hour: Optional[Any] = None,
    minute: Optional[Any] = None,
    second: Optional[Any] = None,
    tz: Optional[Any] = None,
) -> CALLBACK_TYPE:
    """Add a listener that will fire if time matches a pattern."""
    # We do not have to wrap the function with time pattern matching logic
    # if no pattern given
    if all(val is None for val in (hour, minute, second)):

        @callback
        def time_change_listener(event: Event) -> None:
            """Fire every time event that comes in."""
            hass.async_run_job(action, event.data[ATTR_NOW])

        return hass.bus.async_listen(EVENT_TIME_CHANGED, time_change_listener)

    matching_seconds = dt_util.parse_time_expression(second, 0, 59)
    matching_minutes = dt_util.parse_time_expression(minute, 0, 59)
    matching_hours = dt_util.parse_time_expression(hour, 0, 23)

    next_time = None

    def calculate_next(now: datetime) -> None:
        """Calculate and set the next time the trigger should fire."""
        nonlocal next_time

        localized_now = now.astimezone(tz) if tz else now
        next_time = dt_util.find_next_time_expression_time(
            localized_now, matching_seconds, matching_minutes, matching_hours
        )

    # Make sure rolling back the clock doesn't prevent the timer from
    # triggering.
    last_now: Optional[datetime] = None

    @callback
    def pattern_time_change_listener(event: Event) -> None:
        """Listen for matching time_changed events."""
        nonlocal next_time, last_now

        now = event.data[ATTR_NOW]

        if last_now is None or now < last_now:
            # Time rolled back or next time not yet calculated
            calculate_next(now)

        last_now = now

        if next_time <= now:
            hass.async_run_job(action, now.astimezone(tz) if tz else now)
            calculate_next(now + timedelta(seconds=1))

    # We can't use async_track_point_in_utc_time here because it would
    # break in the case that the system time abruptly jumps backwards.
    # Our custom last_now logic takes care of resolving that scenario.
    return hass.bus.async_listen(EVENT_TIME_CHANGED, pattern_time_change_listener)


@callback
@bind_hass
def async_track_time_change_in_tz(
    hass: HomeAssistant,
    action: Callable[..., None],
    hour: Optional[Any] = None,
    minute: Optional[Any] = None,
    second: Optional[Any] = None,
    tz: Optional[Any] = None,
) -> CALLBACK_TYPE:
    """Add a listener that will fire if UTC time matches a pattern."""
    return async_track_utc_time_change(hass, action, hour, minute, second, tz)
