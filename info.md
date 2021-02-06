## nordpool custom component for home assistant

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
    # this is only need if you want a sensor in a non local currecy
    currency: "EUR"

    # Helper so you can set your "low" price
    # low_price = hour_price < average * low_price_cutoff
    low_price_cutoff: 0.95

    # What power regions your are interested in.
    # Possible values: "DK1", "DK2", "FI", "LT", "LV", "Oslo", "Kr.sand", "Bergen", "Molde", "Tr.heim", "Tromsø", "SE1", "SE2", "SE3","SE4", "SYS"
    region: "Kr.sand"

    # How many decimals to use in the display of the price
    precision: 3 

    # What the price should be displayed in default
    # Possible values: mWh, kWh and W
    # default: kWh
    price_type: kWh

    friendly_name: "Power"
      
```

run the create_template script if you want one sensors for each hour. See the help options with ```python create_template --help```
