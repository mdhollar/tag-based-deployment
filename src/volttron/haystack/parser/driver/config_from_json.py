import copy
import json
import re
from collections import defaultdict

from volttron.haystack.parser.driver.base.config_base import \
    DriverConfigGenerator


class JsonDriverConfigGenerator(DriverConfigGenerator):
    """
    Class that parses haystack tags from two json files - one containing tags
    for equipments/devices and another containing haystack tags for points
    This is a reference implementation to show case driver config generation
    based on haystack tags. This class can be extended and customized for
    specific device types and configurations
    For example, override self.driver_config_template and
    self.generate_config_from_template() if you want to generate
    driver configurations for bacnet or modbus drivers
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
        self.equip_id_device_name_map = dict()
        self.equip_id_device_id_map = dict()
        # List of all ahus equip ids
        self.ahu_list = []
        # List of all vav equip ids
        self.vav_list = []
        self.ahu_name_pattern = re.compile(r"\[\d+\]")

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
        # TODO add ahu without vav
        return ahu_dict

    def get_nf_device_id_and_name(self, equip_id, equip_type="vav"):

        if not self.equip_id_device_name_map:
            # Load it once and use it from map from next call
            rows = self.points_json['rows']
            for _d in rows:
                id_list = _d["id"].split(".")
                device = id_list[-2] if id_list else ""
                if _d["equipRef"] in self.vav_list:
                    self.equip_id_device_name_map[_d["equipRef"]] = \
                        self.get_object_name_from_topic(_d["topic_name"],
                                                        "vav")
                    self.equip_id_device_id_map[_d["equipRef"]] = \
                            _d["topic_name"].split("/")[4]
                elif _d["equipRef"] in self.ahu_list:
                    try:
                        self.equip_id_device_name_map[_d["equipRef"]] = \
                            self.get_object_name_from_topic(_d["topic_name"],
                                                            "ahu")
                        self.equip_id_device_id_map[_d["equipRef"]] = \
                            _d["topic_name"].split("/")[4]
                    except ValueError:
                        # ignore as some points might not follow the pattern
                        # for topic name. As long as we find a single point
                        # with topic name matching the pattern we will use that
                        continue

        return self.equip_id_device_id_map[equip_id], self.equip_id_device_name_map[equip_id]

    # To be overridden by subclass if there is custom site specific parsing logic
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

    def generate_ahu_configs(self, ahu_id, vavs):
        final_mapper = dict()
        ahu = ahu_id.split(".")[-1]
        # First create the config for the ahu
        topic = self.ahu_topic_pattern.format(ahu)
        # replace right variables in driver_config_template
        print(f"AHU id is {ahu_id}")
        final_mapper[topic] = self.generate_config_from_template(ahu_id, "ahu")

        # Now loop through and do the same for all vavs
        for vav_id in vavs:
            vav = vav_id.split(".")[-1]
            topic = self.vav_topic_pattern.format(ahu, vav)
            # replace right variables in driver_config_template
            final_mapper[topic] = self.generate_config_from_template(vav_id)
        return ahu, final_mapper

    def generate_config_from_template(self, equip_id, equip_type="vav"):
        device_id, device_name = self.get_nf_device_id_and_name(equip_id,
                                                                equip_type)
        driver = copy.deepcopy(self.config_template)
        nf_query_format = driver["driver_config"]["query"]
        nf_query = nf_query_format.format(device_id=device_id,
                                          obj_name=device_name)
        driver["driver_config"]["query"] = nf_query
        return driver


if __name__ == '__main__':
    d = JsonDriverConfigGenerator(
        "/home/volttron/git/intellimation/intellimation_tcf/configurations/driver/driver.config.file")
    d.generate_configs()
