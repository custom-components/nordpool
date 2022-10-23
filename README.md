# Price Analyzer based on Nordpool Prices for Home Assistant
Shamelessly based on a fork from the wonderful https://github.com/custom-components/nordpool

If you like this, you can [buy me a beer](http://paypal.me/erlendsellie) or a [Ko-fi](https://ko-fi.com/erlendsellie).

If you like being in control of your electricity usage, sign up for Tibber using my my referral link, and get 50 EUR off smart home gadgets in their store:
[https://invite.tibber.com/yuxfw0uu](https://invite.tibber.com/yuxfw0uu)

PriceAnalyzer keeps your energy bill down, by analyzing the prices from Nordpool, and provides you sensors to automatically control your climate entities and hot water heater.

## PriceAnalyzerSensor
Price Analyzer creates sensor a with the recommended temperature correction for your thermostats, based on todays and tomorrows prices, between 1 and -1 degrees celcius.
This is meant to work kind of like Tibbers smart control for thermostats. If the price is going up in an hour or two, it will boost the thermostat. If there is a peak, or the price is falling soon, the thermostat will 'cool down a bit' to save power. 

The sensor looks a lot like the nordpool-sensor, with a list of todays and tomorrows prices, but also includes info about the hour like:
- if the price is gaining later
- if the price is falling later
- the next hours price
- if the price for that hour is over peak price.
- if the price for that hour is over off peak 1 price.
- If the price is the lowest price in the foreseeable future

## Hot water Heater sensor
A sensor for the recommended thermostat setting for your smartified hot water heater with temperature monitoring.
This sensor will calculate when to heat the tank to max, and when to just keep the tank 'hot enough', based on todays and tomorrows prices.
You can provide your own temperatures for the sensor when setting up or editing the PriceAnalyzer integration. The default config is as follows:

```
{
	"default_temp": 75,
	"five_most_expensive": 40,
	"is_falling": 50,
	"five_cheapest": 70,
	"ten_cheapest": 65,
	"low_price": 60,
	"not_cheap_not_expensive": 50,
	"min_price_for_day": 75
}
```
The default config may not suit your hot water heater and use-case, and will depend on how frequent your household take showers, how big the tank is, and where the temperature sensor(s) are placed. This config has worked great for me, have never given me a cold shower.

The config can also be configured as binary on/off, if you don't have a temperature sensor on your water heater, like this: 

```
{
	"default_temp": "on",
	"five_most_expensive": "off",
	"is_falling": "off",
	"five_cheapest": "on",
	"ten_cheapest": "on",
	"low_price": "on",
	"not_cheap_not_expensive": "on",
	"min_price_for_day": "on"
}
```
Keep in mind that without temperature sensors on the heater, a cold shower can occur.

## Installation

### Option 1: HACS

Under HACS -> Integrations, select the 'Three dots' icon in the top right corner, select 'Custom Repository', and add 'https://github.com/erlendsellie/priceanalyzer/' as an integration (category).
It will searchable as 'priceanalyzer'. Click it, and select 'Download this repository with Hacs'.
Then restart Home Assistant, and go to the integrations page to configure it.
It will then create a new sensor, sensor.priceanalyzer in your installation.


Takes the same input as the nordpool component, except for:
- Percent difference between Min and Max for the day before bothering
- Settings for custom degrees for Hot Water sensor
- Minimum max price for the day before PriceAnalyzer Hot Water is active


## Upcoming / TODO:
Pause / Abort: Add a switch entity to abort or pause PriceAnalyzer for the rest of the day, in case you see that it miscalculates, or that you want to override it. This can always be done by templating in HA, but it should be supported natively.



### How-to

For the PriceAnalyzer / thermostat sensor:
Create an Input Number, to use as a target temperature for the climate-entity/thermostat you want to control with priceanalyzer. 
Follow this to create an input number:

[![Create Input Helper.](https://my.home-assistant.io/badges/helpers.svg)](https://my.home-assistant.io/redirect/helpers/)

Then, import this blueprint, and choose your newly created input number, the priceanalyzer sensor, and the climate entity you want to control.

[![Then, use this blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ferlendsellie%2Fpriceanalyzer%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Fpriceanalyzer%2Fpriceanalyzer.yaml)

Now, whenever the price goes up or down, PriceAnalyzer will change the temperature based on the price.



Blueprint for the hot water heater sensor:

[![Hot water heater sensor blueprint.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ferlendsellie%2Fpriceanalyzer%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Fpriceanalyzer%2Fpriceanalyzer_vvb.yaml)



### Apex Charts:

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

### Additional Costs
Add a template as additional costs, and PriceAnalyzer will also evaluate changes in grid price. This example is from MøreNett, where the Gridprice is cheaper at night:

```
{%set hour = now().hour%}
{%set extra = 0.01%}
{%set price = extra%}
{%if hour > 21 or hour < 6%}
  {%set price = price + 0.1375 %}
{%else%}
  {%set price = price + 0.2125 %}
{% endif %}
{{price | round(4)}}
```

Example for adding the difference between day and night for the grid price tariff for Tensio: 
```
{%set hour = now().hour%}
{%if hour > 21 or hour < 6%}
  {{ 0.01 }}
{%else%}
  {{0.0787 + 0.01 }}
{% endif %}

```

### Debug logging

Add this to your configuration.yaml to debug the component.

```
logger:
  default: info
  logs:
    nordpool: debug
    custom_components.priceanalyzer: debug
```

