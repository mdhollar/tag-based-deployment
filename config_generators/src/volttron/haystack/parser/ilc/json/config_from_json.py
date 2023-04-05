import copy
import json
import re
from collections import defaultdict
import sys

from volttron.haystack.parser.ilc.config_base import \
    ILCConfigGenerator


class JsonILCConfigGenerator(ILCConfigGenerator):
    """
    Class that parses haystack tags from two json files - one containing tags
    for equipments/devices and another containing haystack tags for points
    This is a reference implementation is to showcase ILC agent configurations
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

    def _populate_equip_details(self):
        """
        Loop through equip json once and grab interested device ids so rest of the code need not loop through it again
        Code looks for site meter and vavs
        """
        rows = self.equip_json['rows']
        for _d in rows:
            if self.power_meter_tag in _d:  # if tagged as whole building power meter
                self.power_meter_id = _d['id']
            elif "vav" in _d: # if it is tagged as vav, get vav and ahu it is associated with
                # TODO should vav without ahu be included
                self.vav_dict[_d["id"]] = _d.get("ahuRef", "")

    def get_building_power_point(self):
        if not self.power_meter_id:
            self._populate_equip_details()
        if self.power_meter_id:
            return self.get_point_name(self.power_meter_id, "power_meter", "WholeBuildingPower")
        else:
            return ""


    # Should be overridden for different sites if parsing logic is different
    # Parsing logic could also depend on equip type
    def get_point_name_from_topic(self, topic, equip_id=None,
                                  equip_type=None):
        point_name_part = topic.split("/")[-1]
        return re.split(r"[\.|:]", point_name_part)[-1]

    def get_point_name(self, equip_id, equip_type, volttron_point_type):
        if not self.equip_id_point_map:
            # Load it once and use it from map from next call
            ahus = set()
            for vav, ahu in self.vav_dict.items():
                ahus.add(ahu)
            rows = self.points_json['rows']
            for _d in rows:
                if not _d.get(self.point_meta_field):
                    # if there is no point type information this point is
                    # not useful to us skip
                    continue
                equip_ref = _d["equipRef"]
                if equip_ref == self.power_meter_id:
                    interested_point_types = [self.building_power_point_type,]
                    type = "building power"
                elif equip_ref in self.vav_dict:
                    interested_point_types = self.point_types_vav
                    type = "vav"
                else:
                    continue
                # if vav or power meter point
                # check if it is a point type we are interested in
                point_type = _d[self.point_meta_field]
                if point_type in interested_point_types:
                    # save the topic name - if none of the mandatory point are available, this topic name
                    # would be logged in unmapped devices file
                    if not self.equip_id_point_topic_map.get(equip_ref):
                        self.equip_id_point_topic_map[equip_ref] = dict()
                    self.equip_id_point_topic_map[equip_ref][point_type] = _d["topic_name"]
                    if not self.equip_id_point_map.get(equip_ref):
                        self.equip_id_point_map[equip_ref] = dict()
                    point_name = self.get_point_name_from_topic(_d["topic_name"])
                    if point_name:
                        self.equip_id_point_map[equip_ref][point_type] = point_name
                    elif point_type == self.point_meta_map["WholeBuildingPower"]:
                        self.unmapped_device_details[equip_ref] = {
                                "type": "Power Meter",
                                "error": "Unable to parse building power point name from topic name",
                                "topic_name": _d["topic_name"]}
                    else:
                        self.unmapped_device_details[equip_ref] = {
                            "type": type,
                            "error": "Unable to get point name from topic",
                            "topic_name": _d["topic_name"]}

        point_type = self.point_meta_map[volttron_point_type]
        point_name = ""
        if self.equip_id_point_map.get(equip_id):
            point_name = self.equip_id_point_map[equip_id].get(point_type, "")
        return point_name

    def get_name_from_id(self, id):
        name = id.split(".")[-1]
        return name

def main():
    if len(sys.argv) != 2:
        print("script requires one argument - path to configuration file")
        exit()
    config_path = sys.argv[1]
    d = JsonILCConfigGenerator(config_path)
    d.generate_configs()


if __name__ == '__main__':
    main()
