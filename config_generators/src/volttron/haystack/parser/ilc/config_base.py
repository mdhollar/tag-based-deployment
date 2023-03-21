import json
import os.path
import sys
from abc import abstractmethod
from volttron.haystack.parser.utils import strip_comments
import copy


class ILCConfigGenerator:
    """
    Base class that parses haystack tags to generate
    ILC agent configurations based on a configuration templates
    """

    def __init__(self, config):
        if isinstance(config, dict):
            self.config_dict = config
        else:
            try:
                with open(config, "r") as f:
                    self.config_dict = json.loads(strip_comments(f.read()))
            except Exception:
                raise

        self.site_id = self.config_dict.get("site_id", "")
        self.building = self.config_dict.get("building", "")
        self.campus = self.config_dict.get("campus", "")
        if not self.building and self.site_id:
            self.building = self.get_name_from_id(self.site_id)
        if not self.campus and self.site_id:
            self.campus = self.site_id.split(".")[-2]

        self.topic_prefix = self.campus + "/" if self.campus else ""
        self.topic_prefix = self.topic_prefix + self.building + "/" if self.building else ""
        self.power_meter_tag = 'siteMeter'
        self.power_meter_name = self.config_dict.get("building_power_meter", "")

        self.power_meter_id = None
        # all vav equip ids and its corresponding ahu ids
        self.vav_dict = dict()

        self.point_meta_map = self.config_dict.get("point_meta_map")
        self.point_meta_field = self.config_dict.get("point_meta_field",
                                                     "miniDis")
        self.building_power_point_type = self.point_meta_map["WholeBuildingPower"]

        self.volttron_point_types_vav = [x for x in self.point_meta_map if x != "WholeBuildingPower"]
        self.vav_point_types = [self.point_meta_map[x] for x in self.volttron_point_types_vav]
        # Initialize point mapping for ilc config
        self.point_mapping = {x: [] for x in self.point_meta_map.keys()}

        # use this dict to give additional details for user to help manually find the issue
        self.unmapped_device_details = dict()
        # For all unmapped devices add topic name details to this variable for error reporting
        self.equip_id_point_topic_map = dict()

        config_template = self.config_dict.get("config_template")
        if not config_template:
            raise ValueError(f"Missing parameter in config:'config_template'")
        self.ilc_template = {
            "campus": self.campus,
            "building": self.building,
            "power_meter": {
                "device_topic": "",
                "point": ""
            },
            "application_category": "Load Control",
            "application_name": "Intelligent Load Control",
            "clusters": [
                {
                    "device_control_config": "config://vav_control.config",
                    "device_criteria_config": "config://vav_criteria.config",
                    "pairwise_criteria_config": "config://vav_criteria_matrix.json",
                    "cluster_priority": 1.0
                }
            ]
        }
        self.ilc_template.update(config_template["ilc_config"])

        self.control_template = config_template["control_config"]

        self.criteria_template = {"device_topic": ""}
        self.criteria_template.update(config_template["criteria_config"])

        # initialize output dir
        default_prefix = self.building + "_" if self.building else ""
        self.output_dir = self.config_dict.get(
            "output_dir", f"{default_prefix}ILC_configs")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
        elif not os.path.isdir(self.output_dir):
            raise ValueError(f"Output directory {self.output_dir} "
                             f"does not exist")
        print(f"Output directory {os.path.abspath(self.output_dir)}")

        # Initialize map of haystack id and nf device name
        self.equip_id_point_map = dict()
        self.equip_id_device_id_map = dict()

    def generate_configs(self):
        """
        Generated all configuration files for ILC agent for a given site
        """
        error = self.generate_ilc_config()
        if error:
            err_file = f"{self.output_dir}/unmapped_device_details"
            with open(err_file, 'w') as outfile:
                json.dump(error, outfile, indent=4)

            sys.stderr.write(f"\nUnable to generate ilc configuration due to missing device or point. "
                             f"Please see {err_file} for details\n")
            sys.exit(1)

        # Generated ilc config. Now generated config with vav details
        self.generate_control_config()
        self.generate_criteria_config()

        if self.unmapped_device_details:
            err_file = f"{self.output_dir}/unmapped_device_details"
            with open(err_file, 'w') as outfile:
                json.dump(self.unmapped_device_details, outfile, indent=4)

            sys.stderr.write(f"\nUnable to generate configurations for all AHUs and VAVs. "
                             f"Please see {err_file} for details\n")
            sys.exit(1)
        else:
            sys.exit(0)

    def generate_ilc_config(self):

        building_power_point = self.get_building_power_point()

        # Success case
        if self.power_meter_id and building_power_point:
            if not self.power_meter_name:
                self.power_meter_name = self.get_name_from_id(self.power_meter_id)
            self.ilc_template["power_meter"]["device_topic"] = self.topic_prefix + self.power_meter_name
            self.ilc_template["power_meter"]["point"] = building_power_point
            with open(f"{self.output_dir}/ilc.config", 'w') as outfile:
                json.dump(self.ilc_template, outfile, indent=4)
            # missing device or point will result in error. So if we wrote the config return
            return None

        #  Error case
        if not self.power_meter_id:
            return{"building_power_meter":
                       {"error": f"Unable to locate building power meter using the tag '{self.power_meter_tag}' "}}

        if not building_power_point:
            return {self.power_meter_id: {"error": f"Unable to locate building power point using the metadata "
                                                   f"{self.building_power_point_type}"}}

    def generate_control_config(self):

        # subset of volttron point types that control config is interested in
        volttron_point_types_vav = ["MinimumAirFlow", "ZoneAirFlowSetpoint", "ZoneCoolingTemperatureSetPoint"]
        control_config = dict()

        for vav_id in self.vav_dict:
            skip_vav = False
            config = copy.deepcopy(self.control_template)
            vav = self.get_name_from_id(vav_id)
            ahu_id = self.vav_dict[vav_id]
            if ahu_id:
                vav_topic = self.get_name_from_id(ahu_id) + "/" + vav
            else:
                vav_topic = vav
            config["device_topic"] = self.topic_prefix + vav_topic
            point_mapping = dict()
            # get vav point name
            for volttron_point_type in volttron_point_types_vav:
                point_name = self.get_point_name(vav_id, "vav", volttron_point_type)
                if point_name:
                    point_mapping[volttron_point_type] = point_name
                else:
                    if not self.unmapped_device_details.get(vav_id):
                        self.unmapped_device_details[vav_id] = {
                           "type": "vav",
                           "error": f"Unable to find point of type {volttron_point_type}/{self.point_mapping[volttron_point_type]}"
                        }
                    skip_vav = True

            if skip_vav:
                # some points are missing, details in umapped_device_details skip vav and move to next
                continue

            # If all necessary points are found go ahead and add it to control config
            volttron_point = config["curtail_settings"]["point"]
            config["curtail_settings"]["point"] = point_mapping[volttron_point]

            # More than 1 curtail possible? should we loop through?
            volttron_point_list = config["device_status"]["curtail"]["device_status_args"]

            # sort the list of point before doing find and replace of volttron point name with actual point names
            # so that we avoid matching substrings. For example find and replace ZoneAirFlowSetpoint before ZoneAirFlow
            volttron_point_list.sort(key=len)

            v_conditions = config["device_status"]["curtail"]["condition"]
            print(volttron_point_list)

            for condition in v_conditions:
                for point in volttron_point_list:
                    condition = condition.replace(point, point_mapping[point])

            point_list = [point_mapping[point] for point in volttron_point_list]

            # replace curtail values with actual point names
            config["device_status"]["curtail"]["device_status_args"] = point_list
            config["device_status"]["curtail"]["condition"] = condition
            control_config[vav_topic] = {vav: config}

        if control_config:
            with open(f"{self.output_dir}/vav_control.config", 'w') as outfile:
                json.dump(control_config, outfile, indent=4)

    def generate_criteria_config(self):

        # subset of volttron point types that control config is interested in
        volttron_point_list = ["MinimumAirFlow", "MaxAirFlow", "ZoneCoolingTemperatureSetPoint",
                                "ZoneTemperature", "ZoneAirFlow"]

        # sort the list of point before doing find and replace of volttron point name with actual point names
        # so that we avoid matching substrings. For example find and replace ZoneAirFlowSetpoint before ZoneAirFlow
        volttron_point_list.sort(key=len)

        criteria_config = dict()

        for vav_id in self.vav_dict:
            skip_vav = False
            curtail_config = {"device_topic": ""}
            curtail_config.update(copy.deepcopy(self.criteria_template))
            vav = self.get_name_from_id(vav_id)
            ahu_id = self.vav_dict[vav_id]
            if ahu_id:
                vav_topic = self.get_name_from_id(ahu_id) + "/" + vav
            else:
                vav_topic = vav
            curtail_config["device_topic"] = self.topic_prefix + vav_topic
            point_mapping = dict()
            # get vav point name
            for volttron_point_type in volttron_point_list:
                point_name = self.get_point_name(vav_id, "vav", volttron_point_type)
                if point_name:
                    point_mapping[volttron_point_type] = point_name
                else:
                    if not self.unmapped_device_details.get(vav_id):
                        self.unmapped_device_details[vav_id] = {
                           "type": "vav",
                           "error": f"Unable to find point of "
                                    f"type {volttron_point_type} using metadata field {self.point_meta_field} and "
                                    f"configured point mapping {self.point_meta_map[volttron_point_type]}"
                        }
                    skip_vav = True

            if skip_vav:
                # some points are missing, details in umapped_device_details skip vav and move to next
                continue

            for key, value_dict in curtail_config.items():
                if key in ["room_type", "device_topic"]:
                    continue
                # else it is an operation - look for operation and operation_args and replace
                # volttron point names with actual point names

                # Replace in "operation"
                value_dict["operation"] = self.replace_point_names(value_dict["operation"],
                                                                   point_mapping,
                                                                   volttron_point_list)

                # Replace in "operation_args"
                if isinstance(value_dict["operation_args"], dict):
                    value_dict["operation_args"]["always"] = self.replace_point_names(
                        value_dict["operation_args"]["always"],
                        point_mapping,
                        volttron_point_list)
                    value_dict["operation_args"]["nc"] = self.replace_point_names(
                        value_dict["operation_args"]["nc"],
                        point_mapping,
                        volttron_point_list)
                else:
                    # it's a list
                    value_dict["operation_args"] = self.replace_point_names(
                        value_dict["operation_args"],
                        point_mapping,
                        volttron_point_list)

            criteria_config[vav_topic] = {vav: curtail_config}

        if criteria_config:
            with open(f"{self.output_dir}/criteria.config", 'w') as outfile:
                json.dump(criteria_config, outfile, indent=4)

    def replace_point_names(self, search_obj, point_mapping, volttron_point_list):
        if isinstance(search_obj, str):
            for point in volttron_point_list:
                search_obj = search_obj.replace(point, point_mapping[point])
            return search_obj

        else:
            new_list = []
            for search_str in search_obj:
                for point in volttron_point_list:
                    search_str = search_str.replace(point, point_mapping[point])
                new_list.append(search_str)
            return new_list

    @abstractmethod
    def get_building_power_point(self):
        pass

    @abstractmethod
    def get_point_name(self, equip_id, equip_type, point_key):
        pass
    
    @abstractmethod
    def get_name_from_id(self, id):
        pass

    @abstractmethod
    def get_ahu_and_vavs(self):
        """
        Should return a list of ahu and vav mappings
        :return: list of tuples with the format [(ahu1, (vav1,vav2..)),...]
                 or dict mapping ahu with vavs with format
                 {'ahu1':(vav1,vav2,..), ...}
        """
        pass
