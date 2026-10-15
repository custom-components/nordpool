"""Price-period averages using a maintained Nord Pool API response fixture."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from statistics import mean
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_utils

from custom_components.nordpool.aio_price import AioPrices
from custom_components.nordpool.const import DOMAIN
from custom_components.nordpool.sensor import PLATFORM_SCHEMA, async_setup_platform


class TestPricePeriods(unittest.IsolatedAsyncioTestCase):
    """The published peak periods are clock-hour ranges, not entry counts."""

    async def test_quarter_hour_periods(self):
        """Reproduce #509 through the API parser and supported YAML setup."""
        await self.check_periods("delivery_period_today.json", 4)

    async def test_hourly_periods(self):
        """Keep the existing hourly data contract unchanged."""
        await self.check_periods("delivery_period_hourly.json", 1)

    async def check_periods(self, fixture, entries_per_hour):
        with tempfile.TemporaryDirectory() as config_dir:
            hass = HomeAssistant(config_dir)
            hass.data[DOMAIN] = object()
            zone = ZoneInfo("Europe/Stockholm")
            original_zone = dt_utils.DEFAULT_TIME_ZONE
            dt_utils.set_default_time_zone(zone)
            self.addCleanup(dt_utils.set_default_time_zone, original_zone)
            response = json.loads(
                (Path(__file__).parent / "fixtures" / fixture).read_text()
            )
            day = datetime.fromisoformat(response["deliveryDateCET"]).replace(
                tzinfo=zone
            )
            api = AioPrices("SEK", None)

            async def fetch_day(data_type, end_date, areas):
                # The actual API permits 204/no data for adjacent dates.
                return response if end_date.date() == day.date() else None

            api._fetch_json = AsyncMock(side_effect=fetch_day)
            data = await api.hourly(end_date=day, areas=["SE3"])
            sensors = []
            config = PLATFORM_SCHEMA(
                {
                    "platform": DOMAIN,
                    "region": "SE3",
                    "currency": "SEK",
                    "VAT": False,
                    "price_type": "MWh",
                    "precision": 3,
                }
            )
            await async_setup_platform(hass, config, sensors.extend)
            sensor = sensors[0]
            sensor._data_today = data["areas"]["SE3"]
            sensor._update()

            prices = [
                row["entryPerArea"]["SE3"] for row in response["multiAreaEntries"]
            ]
            self.assertEqual(len(prices), 24 * entries_per_hour)
            first = 8 * entries_per_hour
            second = 20 * entries_per_hour
            self.assertAlmostEqual(sensor._off_peak_1, mean(prices[:first]))
            self.assertAlmostEqual(sensor._peak, mean(prices[first:second]))
            self.assertAlmostEqual(sensor._off_peak_2, mean(prices[second:]))
            self.assertAlmostEqual(sensor._average, mean(prices))
