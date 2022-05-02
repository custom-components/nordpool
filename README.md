# Price Analyzer based on Nordpool Prices for Home Assistant
# Shamelessly based on a fork from https://github.com/custom-components/nordpool, as i don't know Python.

Price Analyzer creates sensor a with the recommended temperature correction for your thermostats, based on todays and tomorrows prices, between 1 and -1 degrees celcius.
This is meant to work kind of like Tibbers smart control for thermostats. If the price is going up in an hour or two, it will boost the thermostat. If there is a peak, or the price is falling soon, the thermostat will 'cool down a bit' to save power. 

The sensor looks a lot like the nordpool-sensor, with a list of todays and tomorrows prices, but also includes info about the hour like:
- if the price is gaining later
- if the price is falling later
- the next hours price
- if the price for that hour is over peak price.
- if the price for that hour is over off peak 1 price.

More stuff will probably come, like recommendations to turn on/off water heater as an attribute.

Initial commit a bit before a release is ready, just as a proof of concept.


## Installation

### Option 1: HACS

Under HACS -> Integrations, select the hamburger menu in the top right corner and add 'https://github.com/erlendsellie/priceanalyzer/' as an integration.
It will searchable as 'priceanalyzer'. Click it, and select 'Download this repository with Hacs'.
Then restart Home Assistant, and go to the integrations page to configure it.
It will then create a new sensor, sensor.priceanalyzer in your installation.

More info to come.

Takes the same input as the nordpool component, as of now.


### Debug loggning
Add this to your configuration.yaml to debug the component.

```
logger:
  default: info
  logs:
    nordpool: debug
    custom_components.priceanalyzer: debug
    custom_components.priceanalyzer.sensor: debug
    custom_components.priceanalyzer.aio_price: debug
```
