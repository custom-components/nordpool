# Prepared Tariff configurations for known providers
This list is a community effort to keep track of working Tariff configurations for power providers in regions supported by NordPool.

# Denmark
In denmark, the price of electricity is the base price, plus a fixed tax "elafgift" and a transportation cost ("transportomkostninger"). 

* In 2022, the "elafgift" is 0.903 DKK/kWh [source](https://skat.dk/skat.aspx?oid=2234584)

Note: The "PSO" tax has been discontinued as of 2022-01-01.

## Radius

* In 2021, the "transportomkostninger" for Radius depend on the time of year and day [source](https://radiuselnet.dk/elkunder/priser-og-vilkaar/tariffer-og-netabonnement/)

* The tax is "low" during:
  * Cost: 0.2363 DKK/kWh
  * April through September
  * October through March, during 00:00-17:00 and 20:00-23:59
* The tax is "high" during:
  * Cost: 0.6307 DKK/kWh
  * October through March, during 17:00-20:00

```jinja
  additional_costs: |-
    # See https://github.com/custom-components/nordpool/blob/master/Tariffs.md
    {% set config = {
        "elafgift": 0.903,
        "low_cost": 0.2363,
        "high_cost": 0.6307
    }
    %}
    {{ config.elafgift + (config.high_cost if (now().month <= 3 or 10 <= now().month) and (17 <= now().hour < 20) else config.low_cost) | float }}
```
