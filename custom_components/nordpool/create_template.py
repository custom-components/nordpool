if __name__ == "__main__":
    import yaml
    import click

    """
    For usage example do: python create_template --help
    """

    @click.command({"help_option_names": ["-h", "--h"]})
    @click.argument('entity_id')
    @click.argument('friendly_name')
    @click.option('--icon', default="mdi:cash", help="The icon you want to use.")
    @click.option('--unit', default="NOK/kWh", help="the currency the sensor should use")
    @click.option('--path', default="result.yaml", help="What path to write the file to.")
    def make_sensors(entity_id, friendly_name, icon, unit, path):
        """A simple tool to make 48 template sensors, one for each hour."""

        head = {"sensor": [{"platform": "template", "sensors": {}}]}

        name = "nordpool_%s_hr_%02d_%02d"
        state_attr = '{{ state_attr("sensor.%s", "%s")[%s] }}'

        for i in range(24):
            sensor = {
                "friendly_name": friendly_name + " today h %s" % (i + 1),
                "icon_template": icon,
                "unit_of_measurement": unit,
                "value_template": state_attr % (entity_id, "today", i),
            }

            head["sensor"][0]["sensors"][name % ("today", i, i + 1)] = sensor

        for z in range(24):
            sensor = {
                "friendly_name": friendly_name + " tomorrow h %s" % (z + 1),
                "icon_template": icon,
                "unit_of_measurement": unit,
                "value_template": state_attr % (entity_id, "tomorrow", z),
            }

            head["sensor"][0]["sensors"][name % ("tomorrow", z, z + 1)] = sensor

        with open(path, "w") as yaml_file:
            yaml.dump(head, yaml_file, default_flow_style=False)
            click.echo("All done, wrote file to %s" % path)

    make_sensors()
