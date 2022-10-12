import copy
import json
import re
import sys
import psycopg2

from volttron.haystack.parser.airsidercx.config_base import \
    AirsideRCxConfigGenerator


class IntellimationAirsideRCxConfigGenerator(AirsideRCxConfigGenerator):
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

        # # AirsideRCx point name to metadata(miniDis/Dis field) map
        # self.point_metadata_map = {
        #     "fan_status": "SaFanCmd", #ahu
        #     "zone_reheat": "RhtVlvPos" or "ElecRht1", or "RhtVlvCmd"# "ElecRht2"??? vav
        #     "zone_damper": "DmpCmd", or "vavDmpPos" #vav
        #     "duct_stcpr": "SaPress", #ahu
        #     "duct_stcpr_stpt": "SaPressSp", #ahu
        #     "sa_temp": "SaTemp", #ahu
        #     "fan_speedcmd": "SaFanSpdCmd", #ahu
        #     "sat_stpt": "SaTempSp" #ahu
        # }
        self.point_meta_map = self.config_dict.get("point_meta_map")
        self.point_meta_field = self.config_dict.get("point_meta_field", "miniDis")
        # Initialize point mapping for airsidercx config
        self.point_mapping = {x: [] for x in self.point_meta_map.keys()}
        self.ahu_points = ["fan_status", "duct_stcpr", "duct_stcpr_stpt",
                           "sa_temp", "sat_stpt", "fan_speedcmd"]
        self.vav_points = ["zone_reheat", "zone_damper"]

    def get_ahu_and_vavs(self):
        query = f"SELECT tags #>>'{{ahuRef}}', json_agg(topic_name) \
        FROM {self.equip_table} \
        WHERE tags->>'ahuRef' is NOT NULL AND tags->>'vav'='m:' "
        if self.site_id:
            query = query + f" AND tags->>'siteRef'='{self.site_id}' "
        query = query + f" GROUP BY tags #>>'{{ahuRef}}'"
        # ahu without vavs are not applicable for AirsideRCx
        return self.execute_query(query)

    def get_topic_by_point_type(self, equip_id, point_key):
        query = f"SELECT topic_name " \
                f"FROM {self.point_table} " \
                f"WHERE tags->>'equipRef'='{equip_id}' " \
                f"AND tags->>'{self.point_meta_field}'=" \
                f"'{self.point_meta_map[point_key]}'"

        result = self.execute_query(query)
        if result:
            # for each device there should be only be one point that matches
            # the point type.
            return result[0][0]
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
        final_config = copy.deepcopy(self.config_template)
        ahu = ahu_id.split(".")[-1]
        final_config["device"]["unit"] = {}
        final_config["device"]["unit"][ahu] = {}
        subdevices = final_config["device"]["unit"][ahu]["subdevices"] = list()
        point_mapping = final_config["arguments"]["point_mapping"]
        # Get ahu point details
        ahu_point_name_map = dict()
        for point_key in self.ahu_points:
            topic = self.get_topic_by_point_type(ahu_id, point_key)
            point_name = self.get_point_name_from_topic(topic)
            point_mapping[point_key] = point_name

        # Initialize vav point mapping to set as there can be more than 1
        for point_key in self.vav_points:
            point_mapping[point_key] = set()

        # Now loop through and populate vav details
        for vav_id in vavs:
            vav = vav_id.split(".")[-1]
            subdevices.append(vav)
            # get vav point name
            for point_key in self.vav_points:
                topic = self.get_topic_by_point_type(vav_id, point_key)
                point_name = self.get_point_name_from_topic(topic)
                point_mapping[point_key].add(point_name)

        # convert set to list before returning i.e. written to file
        for point_key in self.vav_points:
            if len(point_mapping[point_key]) > 1:
                point_mapping[point_key] = list(point_mapping[point_key])
            else:
                point_mapping[point_key] = point_mapping[point_key].pop()

        return ahu, final_config


def main():
    if len(sys.argv) != 2:
        print("script requires one argument - path to configuration file")
        exit()
    config_path = sys.argv[1]
    d = IntellimationAirsideRCxConfigGenerator(config_path)
    d.generate_configs()


if __name__ == '__main__':
    main()
