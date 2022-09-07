# Price Analyzer based on Nordpool Prices for Home Assistant
#### Shamelessly based on a fork from https://github.com/custom-components/nordpool, as i don't know Python.

If you like this, [buy me a beer.](http://paypal.me/erlendsellie).

If you like being in control of your electricity usage, sign up for Tibber using my my referral link, and get 50 EUR off smart home gadgets in their store:
[https://invite.tibber.com/yuxfw0uu](https://invite.tibber.com/yuxfw0uu)


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


If you have any input, i'm happy to hear about it. This 'algorithm' has worked great for me over the last two years, but has changed a lot every now and then.

## Installation

### Option 1: HACS

Under HACS -> Integrations, select the 'Three dots' icon in the top right corner, select 'Custom Repository', and add 'https://github.com/erlendsellie/priceanalyzer/' as an integration (category).
It will searchable as 'priceanalyzer'. Click it, and select 'Download this repository with Hacs'.
Then restart Home Assistant, and go to the integrations page to configure it.
It will then create a new sensor, sensor.priceanalyzer in your installation.


Takes the same input as the nordpool component, as of now.


## Upcoming / TODO:
Pause / Abort: Add a switch entity to abort or pause PriceAnalyzer for the rest of the day, in case you see that it miscalculates, or that you want to override it. This can always be done by templating in HA, but it should be supported natively.



### How-to

Create an Input Number, to use as a target temperature for the climate-entity/thermostat you want to control with priceanalyzer. 
Follow this to create an input number:

[![Create Input Helper.](https://my.home-assistant.io/badges/helpers.svg)](https://my.home-assistant.io/redirect/helpers/)

Then, import this blueprint, and choose your newly created input number, the priceanalyzer sensor, and the climate entity you want to control.

[![Then, use this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ferlendsellie%2FHomeAssistantConfig%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Ferlendsellie%2Fpriceanalyzer.yaml)



Now, whenever the price goes up or down, PriceAnalyzer will change the temperature based on the price.

![Apex Card Example](priceanalyzer.png?raw=true "Apex Card Example")

Add this Apex Charts Card to see the schedule for the sensor for today and tomorrow(if available):

```
type: custom:apexcharts-card
header:
  show_states: true
  title: PriceAnalyzer
  show: true
now:
  show: true
graph_span: 48h
span:
  start: day
apex_config:
  chart:
    height: 500
  stroke:
    width: 1
  yaxis:
    - show: true
      id: pris
      decimalsInFloat: 0
      floating: false
      forceNiceScale: true
      extend_to: end
      min: auto
      max: auto
    - decimalsInFloat: 0
      id: binary
      floating: true
      forceNiceScale: true
      extend_to: now
      show: false
      opposite: true
      max: 1000
      min: 0
series:
  - entity: sensor.priceanalyzer
    yaxis_id: pris
    extend_to: now
    name: Price
    unit: Øre/kWh
    curve: stepline
    color: tomato
    show:
      legend_value: false
      in_header: false
    data_generator: |
      let today =  entity.attributes.raw_today.map((entry) => {
        return [new Date(entry.start), (entry.value) * 100];
      });
      if(entity.attributes.tomorrow_valid) {
      let tomorrow = entity.attributes.raw_tomorrow.map((entry) => {
              return [new Date(entry.start), (entry.value) * 100];
            });
        return today.concat(tomorrow);
      }
      return today;
  - entity: sensor.priceanalyzer
    yaxis_id: binary
    name: Opp
    type: area
    curve: stepline
    color: '#00360e'
    opacity: 1
    show:
      in_header: false
      legend_value: false
    data_generator: |
      let today =  entity.attributes.raw_today.map((entry) => {
        return [new Date(entry.start), ((entry.temperature_correction > 0 ? 1 : 0) * 10000)];
      });
      if(entity.attributes.tomorrow_valid) {

        let tomorrow = entity.attributes.raw_tomorrow.map((entry) => {
          return [new Date(entry.start), ((entry.temperature_correction > 0 ? 1 : 0) * 10000)];
        });
        return today.concat(tomorrow);
      }
      return today;
  - entity: sensor.priceanalyzer
    yaxis_id: binary
    name: Ned
    type: area
    curve: stepline
    color: '#4f0500'
    opacity: 1
    show:
      in_header: false
      legend_value: false
    data_generator: |
      let today =  entity.attributes.raw_today.map((entry) => {
        return [new Date(entry.start), ((entry.temperature_correction < 0 ? 1 : 0))];
      });
      if(entity.attributes.tomorrow_valid) {

        let tomorrow = entity.attributes.raw_tomorrow.map((entry) => {
          return [new Date(entry.start), ((entry.temperature_correction < 0 ? 1 : 0))];
        });
        return today.concat(tomorrow);
      }
      return today;
```



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

