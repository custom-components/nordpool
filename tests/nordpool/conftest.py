from unittest.mock import patch


import pytest

from pytest_homeassistant_custom_component.test_util.aiohttp import mock_aiohttp_client
from pytest_homeassistant_custom_component.common import load_fixture


@pytest.fixture
def aioclient_mock():
    """Fixture to mock aioclient calls."""
    with mock_aiohttp_client() as mock_session:
        yield mock_session


MOCK_CONFIG = {
    "region": "Kr.sand",
    "VAT": True,
    "precision": 3,
    "low_price_cutoff": 3,
    "price_in_cents": False,
    "price_type": "kWh",
    "additional_costs": "",
}


# This fixture enables loading custom integrations in all tests.
# Remove to enable selective use of this fixture
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


# This fixture is used to prevent HomeAssistant from attempting to create and dismiss persistent
# notifications. These calls would fail without this fixture since the persistent_notification
# integration is never loaded during a test.
@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip notification calls."""
    with patch("homeassistant.components.persistent_notification.async_create"), patch(
        "homeassistant.components.persistent_notification.async_dismiss"
    ):
        yield
