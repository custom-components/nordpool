## nordpool custom component for home assistant

### Usage


in configuration.yaml
```
nordpool:
  # Default to nok. Possible values are DKK, SEK, NOK and EUR
  currency: "NOK"


```

```
sensor:
  - platform: nordpool
    # Should the prices include vat
    # default True
    VAT: True

    # What currency the api fetches the prices in
    # Helper so you can set your "low" price
    # low_price = hour_price < average * low_price_cutoff
    low_price_cutoff: 0.95
    # What power regions your are interested in. default Kr.sand
    region: "Kr.sand"
      
```
