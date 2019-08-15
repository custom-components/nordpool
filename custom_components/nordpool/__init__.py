import logging

import pendulum
from .misc import *

from homeassistant.const import CONF_CURRENCY
import voluptuous as vol

DOMAIN = "Nordpool"
_LOGGER = logging.getLogger(__name__)

_CURRENCY_LIST = ["DKK", "EUR", "NOK", "SEK"]


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {vol.Required(CONF_CURRENCY, default="NOK"): vol.In(_CURRENCY_LIST)}
        )
    },
    extra=vol.ALLOW_EXTRA,
)


NAME = DOMAIN
VERSION = '0.0.1'
ISSUEURL = 'https://github.com/Hellowlol/nordpool/issues'

STARTUP = """
-------------------------------------------------------------------
{name}
Version: {version}
This is a custom component
If you have any issues with this you need to open an issue here:
{issueurl}
-------------------------------------------------------------------
""".format(name=NAME, version=VERSION, issueurl=ISSUEURL)


class NordpoolData:
    def __init__(self, currency):
        self.currency = currency
        self._data_tomorrow = None
        self._data_today = None
        self.spot = None
        self._last_update_tomorrow_date = None
        self._last_tick = None

    def update(self, force=False):
        from nordpool import elspot

        if self._last_update_tomorrow_date is None:
            if pendulum.now("Europe/Stockholm") > pendulum.now("Europe/Stockholm").at(14):
                self._last_update_tomorrow_date = pendulum.tomorrow("Europe/Stockholm").at(14)
            else:
                self._last_update_tomorrow_date = pendulum.today("Europe/Stockholm").at(14)

        if self._last_tick is None:
            self._last_tick = pendulum.now()

        if self.spot is None:
            self.spot = elspot.Prices(self.currency)

        if force:
            data = self.spot.hourly(end_date=pendulum.now())
            self._data_today = data["areas"]

            data = self.spot.hourly()
            if data:
                self._data_tomorrow = data["areas"]

        if self._data_today is None:
            data = self.spot.hourly(end_date=pendulum.now())
            self._data_today = data["areas"]

        if self._data_tomorrow is None:
            # needs fix
            if pendulum.now("Europe/Stockholm") > pendulum.now("Europe/Stockholm").at(14):
                self._last_update_tomorrow_date = pendulum.tomorrow("Europe/Stockholm").at(14)
                data = self.spot.hourly()
                if data:
                    self._data_tomorrow = data["areas"]
            else:
                _LOGGER.info("New api data for tomorrow isnt posted yet")

        if (self._last_tick.in_timezone("Europe/Stockholm") > self._last_update_tomorrow_date):
            self._last_update_tomorrow_date = pendulum.tomorrow("Europe/Stockholm").at(14)
            data = self.spot.hourly(pendulum.now().add(days=1))
            if data:
                _LOGGER.info(
                    "New data was posted updating tomorrow prices in NordpoolData"
                )
                self._data_tomorrow = data["areas"]

        if is_new(self._last_tick, typ="day"):
            self._data_today = self._data_tomorrow

        self._last_tick = pendulum.now()

    def today(self, area=None):
        self.update()
        return self._data_today.get(area, self._data_today)

    def tomorrow(self, area=None):
        self.update()
        if self._data_tomorrow is not None:
            return self._data_tomorrow.get(area, self._data_tomorrow)


def setup(hass, config):
    """Setup the integration"""
    currency = config.get(CONF_CURRENCY, "NOK")
    api = NordpoolData(currency)
    hass.data[DOMAIN] = api
    _LOGGER.info(STARTUP)
    # Return boolean to indicate that initialization was successful.
    return True
