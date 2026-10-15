"""Device information for the supported YAML and config-entry setup paths.

Run with: python -m unittest discover -s tests
"""

import logging
import tempfile
import unittest
from datetime import timedelta
from types import MappingProxyType

from homeassistant.config_entries import ConfigEntry, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.nordpool.const import DOMAIN
from custom_components.nordpool.sensor import (
    PLATFORM_SCHEMA,
    async_setup_entry,
    async_setup_platform,
)


class TestSensorDeviceInfo(unittest.IsolatedAsyncioTestCase):
    """Only config-entry entities may be associated with a device."""

    async def asyncSetUp(self):
        self.config_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.config_dir.cleanup)
        self.hass = HomeAssistant(self.config_dir.name)
        await entity_registry.async_get(self.hass).async_load()
        # Setup only constructs the sensor; no Nord Pool requests are needed.
        self.hass.data[DOMAIN] = object()
        self.platform = EntityPlatform(
            hass=self.hass,
            logger=logging.getLogger(__name__),
            domain="sensor",
            platform_name=DOMAIN,
            platform=None,
            scan_interval=timedelta(seconds=30),
            entity_namespace=None,
        )
        self.entities = []

    def add_entities(self, entities):
        for entity in entities:
            entity.add_to_platform_start(self.hass, self.platform, None)
            self.entities.append(entity)

    async def test_yaml_does_not_attach_device(self):
        """The documented minimal YAML config has no config entry (#531)."""
        config = PLATFORM_SCHEMA({"platform": DOMAIN, "region": "EE"})
        await async_setup_platform(self.hass, config, self.add_entities)
        sensor = self.entities[0]
        self.assertIsNone(sensor.device_info)
        self.assertEqual(sensor.unique_id, "nordpool_kwh_ee_eur_3_10_024")
        self.assertEqual(sensor.unit_of_measurement, "EUR/kWh")

    async def test_config_entry_keeps_device(self):
        """UI setup retains its existing device identity and metadata."""
        self.platform.config_entry = ConfigEntry(
            domain=DOMAIN,
            title="Nordpool",
            data={
                "region": "EE",
                "currency": "EUR",
                "VAT": True,
                "precision": 3,
                "low_price_cutoff": 1.0,
                "price_in_cents": False,
                "price_type": "kWh",
                "additional_costs": "{{0.0|float}}",
            },
            options={},
            source=SOURCE_USER,
            unique_id=None,
            version=1,
            minor_version=1,
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
        )
        await async_setup_entry(
            self.hass, self.platform.config_entry, self.add_entities
        )
        sensor = self.entities[0]
        self.assertEqual(
            sensor.device_info,
            {
                "identifiers": {(DOMAIN, sensor.unique_id)},
                "name": sensor.name,
                "manufacturer": DOMAIN,
            },
        )
        self.assertEqual(sensor.unique_id, "nordpool_kwh_ee_eur_3_10_024")
        self.assertEqual(sensor.unit_of_measurement, "EUR/kWh")
