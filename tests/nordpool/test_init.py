"""Test nordpool setup process."""
from datetime import timedelta


from homeassistant.exceptions import ConfigEntryNotReady
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

import homeassistant.util.dt as dt_util

from custom_components.nordpool import (
    NordpoolData,
    DOMAIN,
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
)

from .conftest import MOCK_CONFIG


async def test_setup(hass):
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    await async_setup_entry(hass, config_entry)

    assert DOMAIN in hass.data

    api = hass.data[DOMAIN]

    # Real tests for now, lets patch or stub it later.
    data_today_ok = await api.update_today(None)
    assert data_today_ok is True

    data_tomorrow_ok = await api.update_tomorrow(None)
    assert data_today_ok is True

    now = dt_util.now()
    async_fire_time_changed(hass, now + timedelta(hours=24))
    await hass.async_block_till_done()
