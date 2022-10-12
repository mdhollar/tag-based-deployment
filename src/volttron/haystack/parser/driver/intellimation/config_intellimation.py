import copy
import sys
import re

import psycopg2
from volttron.haystack.parser.driver.config_base import \
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

    def generate_config_from_template(self, equip_id, equip_type):
        device_id, device_name = self.query_device_id_name(equip_id,
                                                           equip_type)
        driver = copy.deepcopy(self.config_template)
        nf_query_format = driver["driver_config"]["query"]
        nf_query = nf_query_format.format(device_id=device_id,
                                          obj_name=device_name)
        driver["driver_config"]["query"] = nf_query
        return driver

    def get_name_from_id(self, id):
        name = id.split(".")[-1]
        return name

def main():
    if len(sys.argv) != 2:
        print("script requires one argument - path to configuration file")
        exit()
    config_path = sys.argv[1]
    d = IntellimationDriverConfigGenerator(config_path)
    d.generate_configs()

if __name__ == '__main__':
    main()
