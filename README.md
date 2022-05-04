# Price Analyzer based on Nordpool Prices for Home Assistant
## Shamelessly based on a fork from https://github.com/custom-components/nordpool, as i don't know Python.

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



### How-to


```
    - id: adjustsokkeltemp
      alias: Climate Sokkel - Adjust temp
      mode: restart
      trigger:
        - platform: homeassistant
          event: start
        - platform: state
          entity_id:
            - sensor.sokkeltemp
            - sensor.priceanalyzer
      action:
        - service: climate.set_temperature
          data_template:
            entity_id: climate.sokkel
            temperature: >-
              {%-set baseTemp = states.input_number.sokkeltemp.state | float(default=0)%}
              {%-set priceanalyzer = states.sensor.priceanalyzer.state | float(default=0)%}
              {{baseTemp + priceanalyzer}}
```
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
  - entity: sensor.priceanalyzer_se2
    yaxis_id: pris
    extend_to: now
    name: Price
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
  - entity: sensor.priceanalyzer_se2
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
  - entity: sensor.priceanalyzer_se2
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

