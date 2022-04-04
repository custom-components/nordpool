from unittest.mock import patch


import pytest

"""

        data_schema = {
            vol.Required("region", default=None): vol.In(regions),
            vol.Optional("currency", default=""): vol.In(currencys),
            vol.Optional("VAT", default=True): bool,
            vol.Optional("precision", default=3): vol.Coerce(int),
            vol.Optional("low_price_cutoff", default=1.0): vol.Coerce(float),
            vol.Optional("price_in_cents", default=False): bool,
            vol.Optional("price_type", default="kWh"): vol.In(price_types),
            vol.Optional("additional_costs", default=""): str,
        }
"""


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


# pytest_plugins = ("myapp.testsupport.myplugin",)
