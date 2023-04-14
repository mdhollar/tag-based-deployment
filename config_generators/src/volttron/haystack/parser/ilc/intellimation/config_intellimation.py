import copy
import json
import re
import sys
import psycopg2

from volttron.haystack.parser.ilc.config_base import ILCConfigGenerator


class IntellimationILCConfigGenerator(ILCConfigGenerator):
    """
    class that parses haystack tags from a postgres db to generate
    ILC configs
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
        self.vavs_and_ahuref = list()

    def get_building_power_meter(self):
        query = f"SELECT tags->>'id' \
                  FROM {self.equip_table} \
                  WHERE tags->>'siteMeter' is NOT NULL AND  tags->>'dis'='s:Electric Meter - Building'"
        if self.site_id:
            query = query + f" AND tags->>'siteRef'='{self.site_id}' "
        print(query)
        result = self.execute_query(query)
        if result:
            return result[0][0]

    def get_building_power_point(self):
        query = f"SELECT tags->>'id' \
                  FROM {self.point_table} \
                  WHERE tags->>'equipRef'='{self.power_meter_id}'"
        print(query)
        result = self.execute_query(query)
        if result:
            return result[0][0]

    def get_vavs_with_ahuref(self):
        if not self.vavs_and_ahuref:
            query = f"SELECT tags->>'id', tags->>'ahuRef'  \
            FROM {self.equip_table} \
            WHERE tags->>'vav'='m:' "
            if self.site_id:
                query = query + f" AND tags->>'siteRef'='{self.site_id}' "

            # ahu without vavs and vav without ahuref are not applicable for AirsideRCx
            self.vavs_and_ahuref = self.execute_query(query)
        return self.vavs_and_ahuref

    def get_topic_by_point_type(self, equip_id, point_key):
        point_type = self.point_meta_map[point_key]
        query = f"SELECT topic_name " \
                f"FROM {self.point_table} " \
                f"WHERE tags->>'equipRef'='{equip_id}' " \
                f"AND tags->>'{self.point_meta_field}'=" \
                f"'{point_type}'"
        result = self.execute_query(query)
        if result:
            # for each device there should be only be one point that matches
            # the point type.
            topic = result[0][0]
            if not self.equip_id_point_topic_map.get(equip_id):
                self.equip_id_point_topic_map[equip_id] = dict()
            self.equip_id_point_topic_map[equip_id][point_type] = topic
            return topic
        else:
            # raise ValueError(
            #     f"No point name with "
            #     f"tag->>'{self.point_meta_field}'="
            #     f"'{self.point_meta_map[point_key]}' found for {equip_id}")
            return ""

    # Should be overridden for different sites if parsing logic is different
    # Parsing logic could also depend on equip type
    def get_point_name_from_topic(self, topic, equip_id=None, equip_type=None):
        point_name_part = topic.split("/")[-1]
        return re.split(r"[\.|:]", point_name_part)[-1]

    def execute_query(self, query):
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            result = cursor.fetchall()
            return result
        except Exception:
            raise
        finally:
            if cursor:
                cursor.close()

    def get_point_name(self, equip_id, equip_type, point_key):
        topic = self.get_topic_by_point_type(equip_id, point_key)
        point_name = self.get_point_name_from_topic(topic)
        return point_name

    def get_name_from_id(self, id):
        name = id.split(".")[-1]
        return name


def main():
    if len(sys.argv) != 2:
        print("script requires one argument - path to configuration file")
        exit()
    config_path = sys.argv[1]
    d = IntellimationILCConfigGenerator(config_path)
    d.generate_configs()


if __name__ == '__main__':
    main()
