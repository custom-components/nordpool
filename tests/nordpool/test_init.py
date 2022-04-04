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
    await async_setup_entry(hass, config_entry)
    await hass.async_block_till_done()

    assert DOMAIN in hass.data

    api = hass.data[DOMAIN]
    print(api)
    # aioclient_mock.get(
    #    "https://www.nordpoolgroup.com/api/marketdata/page/10?currency=NOK&endDate=27-03-2022",
    #    json=load_fixture("raw_data_nok_summertime.json"),
    # )

    a = AioPrices(None, "NOK")
    a.currency = "NOK"

    def wrap():
        data = defaultdict(dict)
        parsed = a._parse_json(json.loads(load_fixture("raw_data_nok_summertime.json")))

        data["NOK"]["today"] = join_result_for_correct_time([parsed], None)
        return data

    # print(wrap())

    m = AsyncMock(return_value=wrap())
    # Find the correct place to patch this..
    with patch("custom_components.nordpool.aio_price.AioPrices.fetch", new=m(),), patch(
        "custom_components.nordpool.sensor.AioPrices.fetch",
        new=m(),
    ), patch("custom_components.nordpool.AioPrices.fetch", new=m()):
        # Real tests for now, lets patch or stub it later.
        data_today_ok = await api.update_today(None)
        print(api._data["today"])
        assert data_today_ok is True

    # data_tomorrow_ok = await api.update_tomorrow(None)
    # assert data_today_ok is True

    # now = dt_util.now()
    # async_fire_time_changed(hass, now + timedelta(hours=24))
    await hass.async_block_till_done()
