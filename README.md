# Nordpool integration for Home Assistant
[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=MAXZPYVPD8XS6)
[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/2ys3cdCZk)

Nord Pool is a service provider that operates an electricity market and power system services, including the exchange of electricity on a spot market Nordics and Baltic countries. 

This integration provides the spot market (hourly) electricity prices for the Nordic, Baltic and part of Western Europe. 

The Nordpool sensor provides the current price with today's and tomorrow's prices as attributes. prices become available around 13:00.

[EpaxCharts](https://github.com/RomRider/apexcharts-card) frontend is recommended for visualization of the data.<br>
<img src="https://user-images.githubusercontent.com/5879533/210006998-d8ebd401-5a92-471d-9072-4e6b1c69b779.png" width="500"/>

### Table of Contents
**[Installation](#installation)**<br>
**[Usage](#usage)**<br>
**[Other](#other)**<br>
**[Troubleshooting](#troubleshooting)**<br>

### Getting started
- Tutorial: [Nordpool and ExaxChart](https://www.creatingsmarthome.com/index.php/2022/09/17/home-assistant-nord-pool-spot-prices-and-how-to-automate-devices-for-cheapest-hours/) by Creating Smart Home
- Community: [Nordpool Energy Prices](https://community.home-assistant.io/t/any-good-ideas-are-welcome-nordpool-energy-price-per-hour/) on Home Assistant Community

## Installation

### Option 1: HACS
- Go to `HACS` -> `Integrations`, 
- select `+`, 
- search for `nordpool` and install it,
- Restart Home Assistant

### Option 2: Manual
From the [latest release](https://github.com/custom-components/nordpool/releases)

```bash
cd YOUR_HASS_CONFIG_DIRECTORY    # same place as configuration.yaml
mkdir -p custom_components/nordpool
cd custom_components/nordpool
unzip nordpool-X.Y.Z.zip
mv nordpool-X.Y.Z/custom_components/nordpool/* .  
```

## Usage

### Configuration Variables
| Configuration        | Required | Description                   | 
|----------------------| -------- | ----------------------------- |
| Region               | yes      | Country/region to get the energy prices for. See Country/region codes below for details.| 
| Currency             | no       | *Default: local currency* <br> Currency used to fetch the prices from the API.|
| Include VAT          | no       | *Default: true* <br> Add Value Added Taxes (VAT) or not.|
| Decimal precision    | no       | *Default: 3* <br> Energy price rounding precision. |
| Low price percentage | no       | *Default: 1* <br> Percentage of average price to set the low price attribute. <br> IF hour_price < average * low_price_cutoff <br> THEN low_price = True <br> ELSE low_price = False|
| Price in cents       | no       | *Default: false* <br> Display price in cents in stead of (for example) Euros.|
| Energy scale         | no       | *Default: kWh* <br> Price displayed for MWh, kWh or Wh.|
| Additional Cost      | no       |  *default `{{0.0\|float}}`* <br> Template to specify additional cost to be added. See [Additional Costs](#additional-costs) for more details.|

### Option 1: UI
- Go to `Settings` -> `Devices & Services`
- Select `+ Add Integration`
- search for `nordpool` and select it
- Fill in the required values and press `Submit`

Tip: By default, the integration will create a device with the name `nordpool_<energy_scale>_<region>_<currency>_<some-numbers>`. It is recommended to rename the device and all its entities to `nordpool`. If you need to recreate your sensor (for example, to change the additional cost), all automations and dashboards keep working.

### Option 2: YAML
Set up the sensor using in `configuration.yaml`.

#### Minimal configuration:
```
sensor:
  - platform: nordpool
    region: "Kr.sand" 
```

#### Example configuration:
```
sensor:
  - platform: nordpool
    # Country/region to get the energy prices for. 
    region: "Kr.sand"
    
    # Override HA local currency used to fetch the prices from the API.
    currency: "EUR"
    
    # Add Value Added Taxes (VAT)?
    VAT: True
    
    # Energy price rounding precision.
    precision: 3
    
    # Percentage of average price to set the low price attribute
    # low_price = hour_price < average * low_price_cutoff
    low_price_cutoff: 0.95

    # Display price in cents in stead of (for example) Euros.
    price_in_cents: false

    # Price displayed for MWh, kWh or Wh
    price_type: kWh

    # Template to specify additional cost to be added to the tariff.
    # The template price is in EUR, DKK, NOK or SEK (not in cents).
    # For example: "{{ current_price * 0.19 + 0.023 | float}}" 
    additional_costs: "{{0.0|float}}"
```
### Regions
See the [Nord Pool region map](https://www.nordpoolgroup.com/en/maps/) for details

| Country   | Region code | 
| --------- | ----------- |
| Austria   | AT |
| Belgium   | BE |
| Denmark   | DK1, <br> DK2|
| Estinia   | EE |
| Finland   | FI |
| France    | FR |
| Germany   | DE-LU |
| Great-Britain | Not yet available in this version |
| Latvia    | LV |
| Lithuania | LT |
| Luxenburg | DE-LU |
| Netherlands | NL |
| Norway    | Oslo (NO1) <br> Kr.sand (NO2) <br> Tr.heim / Molde (NO3) <br> Tromso (NO4) <br> Bergen (NO5)  |
| Poland    | Not yet available in this version |
| Sweden    | SE1, <br> SE2, <br> SE3, <br> SE4 |

### Additional costs
The idea behind a addition_costs is to allow the users to add costs related to the official price from Nordpool. 
- Add simple or complex tariffs
- Calculate VAT

There are two special special arguments in that can be used in the template [(in addition to all default from Homeassistant](https://www.home-assistant.io/docs/configuration/templating/)):
- ```now()```- this always refer to the current hour of the price
- ```current_price``` Price for the current hour. This can be used for example be used to calculate your own VAT or add overhead cost. 

Note: When configuring nordpool using the UI, things like VAT and additional costs cannot be changes. If your energy supplier or region changes the cost or rules on a semi-regular basis, the YAML configuration might be better for you.

#### Example 1: Percentage (VAT)
Add 19 % VAT of the current hour's price 

```{{current_price * 0.19}}```

#### Example 2: Overhead per kWh

Add 1,3 cents per kWh overhead cost to the current hour's price 

```{{current_price + 0.013}}```

#### Example 3: Seasonal peek and off-peek overhead

```
{% set s = {
    "hourly_fixed_cost": 0.5352,
    "winter_night": 0.265,
    "winter_day": 0.465,
    "summer_day": 0.284,
    "summer_night": 0.246,
    "cert": 0.01
}
%}
{% if now().month >= 5 and now().month < 11 %}
    {% if now().hour >= 6 and now().hour < 23 %}
        {{ s.summer_day + s.hourly_fixed_cost + s.cert | float }}
    {% else %}
        {{ s.summer_night + s.hourly_fixed_cost + s.cert|float }}
    {% endif %}
{% else %}
    {% if now().hour >= 6 and now().hour < 23 %}
        {{ s.winter_day + s.hourly_fixed_cost + s.cert | float }}
    {% else %}
        {{ s.winter_night + s.hourly_fixed_cost + s.cert | float }}
    {% endif %}
{% endif %}
```

## Other

### A sensor per hour

By default, one sensor is created with the current energy price. The prices for other hours are stored in the attriutes of this sensor. Most example code you will find use the default one sensor option, but you can create a sensor for every hour if you want.

run the create_template script if you want one sensors for each hour. 

See the help options with ```python create_template --help``` you can run the script anyhere python is installed. (install the required packages pyyaml and click using `pip install packagename`)

## Troubleshooting

### Debug logging
Add this to your configuration.yaml to debug the component.

```
logger:
  default: info
  logs:
    nordpool: debug
    custom_components.nordpool: debug
    custom_components.nordpool.sensor: debug
    custom_components.nordpool.aio_price: debug
```
