import copy
import json
import re

import psycopg2
from volttron.haystack.parser.driver.base.config_base import \
    DriverConfigGenerator


class IntellimationDriverConfigGenerator(DriverConfigGenerator):
    """
    class that parses haystack tags from a postgres db to generate
    platform driver configuration for normal framework driver type
    """
    def __init__(self, config):
        super().__init__(config)

        # get details on haystack metadata
        metadata = self.config_dict.get("metadata")
        connect_params = metadata.get("connection_params")
        if "timescale_dialect" in metadata:
            self.timescale_dialect = metadata.get("timescale_dialect",
                                                  False)
            del connect_params["timescale_dialect"]
        else:
            self.timescale_dialect = False
        self.connection = psycopg2.connect(**connect_params)
        self.connection.autocommit = True
        self.equip_table = metadata.get("equip_table")
        self.point_table = metadata.get("point_table")
        self.site_id = metadata.get("site_id", "")
        self.ahu_name_pattern = re.compile(r"\[\d+\]")

    def get_ahu_and_vavs(self):
        query = f"SELECT tags #>>'{{ahuRef}}', json_agg(topic_name) \
        FROM {self.equip_table} \
        WHERE tags->>'ahuRef' is NOT NULL AND tags->>'vav'='m:' "
        if self.site_id:
            query = query + f" AND tags->>'siteRef'='{self.site_id}' "
        query = query + f" GROUP BY tags #>>'{{ahuRef}}'"
        # TODO - add ahu without vavs
        return self.execute_query(query)

    def query_device_id_name(self, equip_id, equip_type):
        query = f"SELECT device_name, topic_name \
                  FROM {self.point_table} \
                  WHERE tags->>'equipRef'='{equip_id}' "
        if self.site_id:
            query = query + f" AND tags->>'siteRef'='{self.site_id}' "
        query = query + " LIMIT 1"

        result = self.execute_query(query)
        if result:
            device_id, topic_name = result[0]
            object_name = self.get_object_name_from_topic(topic_name,
                                                          equip_type)
            return device_id, object_name

    def get_object_name_from_topic(self, topic_name, equip_type):
        # need device name only if device id is not unique
        if "attr_prop_object_name" in \
                self.config_template["driver_config"]["query"]:
            if equip_type == "ahu":
                part = topic_name.split("/")[-1]
                m = re.search(self.ahu_name_pattern, part)
                if m is None:
                    raise ValueError(
                        f"Unable to ahu object name from {topic_name} "
                        f"using pattern {self.ahu_name_pattern}")
                match = m.group(0)
                return match.replace("[", "(").replace("]", ")")
            else:
                return topic_name.split("/")[-1].split(":")[0]
        return ""

    def execute_query(self, query):
        cursor = self.connection.cursor()
        try:
            print(query)
            cursor.execute(query)
            result = cursor.fetchall()
            print(result)
            return result
        except Exception:
            raise
        finally:
            if cursor:
                cursor.close()

    def generate_ahu_configs(self, ahu_id, vavs):
        final_mapper = dict()
        ahu = ahu_id.split(".")[-1]
        # First create the config for the ahu
        topic = self.ahu_topic_pattern.format(ahu)
        # replace right variables in driver_config_template
        final_mapper[topic] = self.generate_config_from_template(ahu_id,
                                                                 "ahu")

        # Now loop through and do the same for all vavs
        for vav_id in vavs:
            vav = vav_id.split(".")[-1]
            topic = self.vav_topic_pattern.format(ahu, vav)
            # replace right variables in driver_config_template
            final_mapper[topic] = self.generate_config_from_template(vav_id,
                                                                     "vav")
        return ahu, final_mapper

    def generate_config_from_template(self, equip_id, equip_type):
        device_id, device_name = self.query_device_id_name(equip_id,
                                                           equip_type)
        driver = copy.deepcopy(self.config_template)
        nf_query_format = driver["driver_config"]["query"]
        nf_query = nf_query_format.format(device_id=device_id,
                                          obj_name=device_name)
        driver["driver_config"]["query"] = nf_query
        return driver


if __name__ == '__main__':
    d = IntellimationDriverConfigGenerator(
        "/home/volttron/git/intellimation/tag_based_setup/configurations/driver.config.db.local")
    d.generate_configs()
