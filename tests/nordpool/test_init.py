"""Test nordpool setup process."""
from unittest.mock import patch, AsyncMock

from datetime import datetime, timedelta
import json
from collections import defaultdict

import aiohttp

from homeassistant.exceptions import ConfigEntryNotReady
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    load_fixture,
)

import homeassistant.util.dt as dt_util

from custom_components.nordpool import (
    DOMAIN,
    async_reload_entry,
    async_setup_entry,
    async_unload_entry,
    AioPrices,
)

from custom_components.nordpool.aio_price import join_result_for_correct_time


from .conftest import MOCK_CONFIG


async def test_setup(hass):
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
    # await async_setup_entry(hass, config_entry)
    # await hass.async_block_till_done()

    # assert DOMAIN in hass.data

    # api = hass.data[DOMAIN]

    # now = dt_util.now()
    # async_fire_time_changed(hass, now + timedelta(hours=24))
    # await hass.async_block_till_done()
