## nordpool custom component for home assistant
[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=MAXZPYVPD8XS6)
[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/2ys3cdCZk)

## Installation

### Option 1: HACS

Under HACS -> Integrations, select "+", search for `nordpool` and install it.


### Option 2: Manual

From the [latest release](https://github.com/custom-components/nordpool/releases)

```bash
cd YOUR_HASS_CONFIG_DIRECTORY    # same place as configuration.yaml
mkdir -p custom_components/nordpool
cd custom_components/nordpool
unzip nordpool-X.Y.Z.zip
mv nordpool-X.Y.Z/custom_components/nordpool/* .  
```


### Usage

Set up the sensor using the webui or use a yaml.

The sensors tries to set some sane default so a minimal setup can be

```
sensor:
  - platform: nordpool
    region: "Kr.sand" # This can be skipped if you want Kr.sand
```



in configuration.yaml

```
nordpool:

sensor:
  - platform: nordpool

    # Should the prices include vat? Default True
    VAT: True

    # What currency the api fetches the prices in
    # this is only need if you want a sensor in a non local currency
    currency: "EUR"
    
    # Option to show prices in cents (or the equivalent in local currency)
    price_in_cents: false

    # Helper so you can set your "low" price
    # low_price = hour_price < average * low_price_cutoff
    low_price_cutoff: 0.95

    # What power regions your are interested in.
    # Possible values: "DK1", "DK2", "FI", "LT", "LV", "Oslo", "Kr.sand", "Bergen", "Molde", "Tr.heim", "Tromsø", "SE1", "SE2", "SE3","SE4", "SYS", "EE"
    region: "Kr.sand"

    # How many decimals to use in the display of the price
    precision: 3

    # What the price should be displayed in default
    # Possible values: MWh, kWh and Wh
    # default: kWh
    price_type: kWh

    # This option allows the usage of a template to add a tariff.
    # now() always refers start of the hour of that price.
    # this way we can calculate the correct costs add that to graphs etc.
    # The price result of the additional_costs template expects this additional cost to be in kWh and not cents as a float
    # default {{0.0|float}}
    additional_costs: "{{0.0|float}}"

```

### Addition costs
The idea behind a addition_costs is to allow the users to add costs related to the official price from Nordpool. 
- Add simple or complex tariffs
- Calculate VAT

There are two special special arguments in that can be used in the template [(in addition to all default from Homeassistant](https://www.home-assistant.io/docs/configuration/templating/)):
- ```now()```- this always refer to the current hour of the price
- ```current_price``` Price for the current hour. This can be used for example be used to calculate your own VAT. Example add 10 % VAT of the current hour's price ```{{current_price * 0.1}}```

##### Tariff example
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
{% if now().month >= 5 and now().month <11 %}
    {% if now().hour >=6 and now().hour <23 %}
        {{s.summer_day+s.hourly_fixed_cost+s.cert|float}}
    {% else %}
        {{s.summer_night+s.hourly_fixed_cost+s.cert|float}}
    {% endif %}
{% else %}
    {% if now().hour >=6 and now().hour <23 %}
        {{s.winter_day+s.hourly_fixed_cost+s.cert|float}}
    {%else%}
        {{s.winter_night+s.hourly_fixed_cost+s.cert|float}}
    {% endif %}
{% endif %}
```


run the create_template script if you want one sensors for each hour. See the help options with ```python create_template --help``` you can run the script anyhere python is installed. (install the required packages pyyaml and click using `pip install packagename`)

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
