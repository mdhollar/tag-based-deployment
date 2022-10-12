import copy
import json
import re
from collections import defaultdict
import sys

from volttron.haystack.parser.airsidercx.config_base import \
    AirsideRCxConfigGenerator


class JsonAirsideRCxConfigGenerator(AirsideRCxConfigGenerator):
    """
    Class that parses haystack tags from two json files - one containing tags
    for equipments/devices and another containing haystack tags for points
    This is a reference implementation to show case airsidercx agent config
    generation based on haystack tags. This class can be extended and
    customized for specific device types and configurations
    """

    def __init__(self, config):
        super().__init__(config)
        # get details on haystack metadata
        metadata = self.config_dict.get("metadata")
        try:
            with open(metadata.get("equip_json"), "r") as f:
                self.equip_json = json.load(f)
            with open(metadata.get("points_json"), "r") as f:
                self.points_json = json.load(f)
        except Exception:
            raise
        # Initialize map of haystack id and nf device name
        self.equip_id_point_map = dict()
        self.equip_id_device_id_map = dict()
        # List of all ahus equip ids
        self.ahu_list = []
        # List of all vav equip ids
        self.vav_list = []

        self.point_meta_map = self.config_dict.get("point_meta_map")
        self.point_meta_field = self.config_dict.get("point_meta_field",
                                                     "miniDis")
        # Initialize point mapping for airsidercx config
        self.point_mapping = {x: [] for x in self.point_meta_map.keys()}
        self.ahu_point_keys = ["fan_status", "duct_stcpr", "duct_stcpr_stpt",
                           "sa_temp", "sat_stpt", "fan_speedcmd"]
        self.vav_point_keys = ["zone_reheat", "zone_damper"]
        self.ahu_point_types = [self.point_meta_map[x] for x in
                                self.ahu_point_keys]
        self.vav_point_types = [self.point_meta_map[x] for x in
                                self.vav_point_keys]

    def get_ahu_and_vavs(self):
        rows = self.equip_json['rows']
        vav_list = []
        ahu_dict = defaultdict(list)
        for _d in rows:
            id_list = _d["id"].split(".")
            device = id_list[-1] if id_list else ""
            if "vav" in device:
                vav_list.append(_d)
                ahu_dict[_d["ahuRef"]].append(_d["id"])
                self.vav_list.append(_d["id"])
        self.ahu_list.extend(ahu_dict.keys())
        # add ahu without vav not relevant for AirsideRcx
        return ahu_dict

    # Should be overridden for different sites if parsing logic is different
    # Parsing logic could also depend on equip type
    def get_point_name_from_topic(self, topic, equip_id=None,
                                  equip_type=None):
        point_name_part = topic.split("/")[-1]
        return re.split(r"[\.|:]", point_name_part)[-1]

    def get_point_name(self, equip_id, equip_type, point_type_meta):
        if not self.equip_id_point_map:
            # Load it once and use it from map from next call
            rows = self.points_json['rows']
            for _d in rows:
                if _d["id"] == "r:@intellimation.dc_dgs.dcps.anacostia_hs.eru-d1_s-wing.onrly1":
                    print("r:@intellimation.dc_dgs.dcps.anacostia_hs.eru-d1_s-wing.onrly1")
                if not _d.get(self.point_meta_field):
                    # if there is no point type information this point is
                    # not useful to us skip
                    continue

                id_list = _d["id"].split(".")
                device = id_list[-2] if id_list else ""
                if _d["equipRef"] in self.vav_list:
                    interested_point_types = self.vav_point_types
                elif _d["equipRef"] in self.ahu_list:
                    interested_point_types = self.ahu_point_types
                else:
                    continue
                # if vav or ahu point
                # check if it is a point type we are interested in
                if _d[self.point_meta_field] in interested_point_types:
                    if not self.equip_id_point_map.get(_d["equipRef"]):
                        self.equip_id_point_map[_d["equipRef"]] = dict()
                    self.equip_id_point_map[_d["equipRef"]][_d[self.point_meta_field]] = \
                             self.get_point_name_from_topic(_d["topic_name"])

        point_type = self.point_meta_map[point_type_meta]
        point_name = self.equip_id_point_map[equip_id].get(point_type, "")
        return point_name

    def generate_ahu_configs(self, ahu_id, vavs):
        final_config = copy.deepcopy(self.config_template)
        ahu = ahu_id.split(".")[-1]
        final_config["device"]["unit"] = {}
        final_config["device"]["unit"][ahu] = {}
        subdevices = final_config["device"]["unit"][ahu]["subdevices"] = list()
        point_mapping = final_config["arguments"]["point_mapping"]
        # Get ahu point details
        ahu_point_name_map = dict()
        for point_key in self.ahu_point_keys:
            point_name = self.get_point_name(ahu_id, "ahu", point_key)
            point_mapping[point_key] = point_name

        # Initialize vav point mapping to set as there can be more than 1
        for point_key in self.vav_point_keys:
            point_mapping[point_key] = set()

        # Now loop through and populate vav details
        for vav_id in vavs:
            vav = vav_id.split(".")[-1]
            subdevices.append(vav)
            # get vav point name
            for point_key in self.vav_point_keys:
                point_name = self.get_point_name(vav_id, "vav", point_key)
                if point_name:
                    point_mapping[point_key].add(point_name)

        # convert set to list before returning i.e. written to file
        for point_key in self.vav_point_keys:
            if not point_mapping[point_key]:
                point_mapping[point_key] = ""
            elif len(point_mapping[point_key]) > 1:
                point_mapping[point_key] = list(point_mapping[point_key])
            else:
                point_mapping[point_key] = point_mapping[point_key].pop()

        return ahu, final_config


def main():
    if len(sys.argv) != 2:
        print("script requires one argument - path to configuration file")
        exit()
    config_path = sys.argv[1]
    d = JsonAirsideRCxConfigGenerator(config_path)
    d.generate_configs()


if __name__ == '__main__':
    main()
