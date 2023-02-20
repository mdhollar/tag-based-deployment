import json
import copy
import os.path
import sys
from abc import abstractmethod
from volttron.haystack.parser.utils import strip_comments


class AirsideEconomizerConfigGenerator:
    """
    Base class that parses haystack tags to generate
    Airside Economizer agent configuration based on a configuration template
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
        self.building = self.config_dict.get("building")
        self.campus = self.config_dict.get("campus")
        if not self.building and self.site_id:
            self.building = self.site_id.split(".")[-1]
        if not self.campus and self.site_id:
            self.campus = self.site_id.split(".")[-2]

        # If there are AHUs without the right point details
        # use this dict to give additional details for user to help manually find the issue.
        # All points are mandatory for airside economizer
        self.unmapped_device_details = dict()
        # For all unmapped devices add topic name details to this variable for error reporting
        self.equip_id_point_topic_map = dict()

        self.config_template = self.config_dict.get("config_template")
        self.config_template["device"] = {
            "campus": self.campus,
            "building": self.building,
            "unit": {}
        }
        # initialize output dir
        default_prefix = self.building + "_" if self.building else ""
        self.output_dir = self.config_dict.get(
            "output_dir", f"{default_prefix}airside_economizer_configs")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
        elif not os.path.isdir(self.output_dir):
            raise ValueError(f"Output directory {self.output_dir} "
                             f"does not exist")
        print(f"Output directory {os.path.abspath(self.output_dir)}")

        # # Airside economizer point name to metadata(miniDis/Dis field) map
        # "supply_fan_status": "s:SaFanCmd",  # supply fan run command
        # "outdoor_air_temperature": "s:OaTemp",
        # "return_air_temperature": "s:RaTemp",
        # "mixed_air_temperature": "s:MATemp",
        # "outdoor_damper_signal": "s:OaDmprCmd",
        # # if 'chilled water valve pos' is not there try 'valve cmd'
        # "cool_call": ["s:ChwVlvPos", "s:ChwVlvCmd"],
        # "supply_fan_speed": "s:SaFanSpdCmd"
        self.point_meta_map = self.config_dict.get("point_meta_map")
        self.point_meta_field = self.config_dict.get("point_meta_field", "miniDis")
        # Initialize point mapping for airsidercx config
        self.point_mapping = {x: "" for x in self.point_meta_map.keys()}

    @abstractmethod
    def get_ahus(self):
        """
        Should return a list of ahus
        :return: list of ahu ids
        """
        pass

    def generate_configs(self):
        results = self.get_ahus()
        print(f"Got ahus as {results}")

        for ahu in results:
            if isinstance(ahu, str):
                ahu_id = ahu
            else:
                # results from db. list of rows, where each element in list is list of columns queried
                ahu_id = ahu[0]
            ahu_name, result_dict = self.generate_ahu_configs(ahu_id)

            if result_dict:
                with open(f"{self.output_dir}/{ahu_name}.json", 'w') as outfile:
                    json.dump(result_dict, outfile, indent=4)

        if self.unmapped_device_details:
            err_file = f"{self.output_dir}/unmapped_device_details"
            with open(err_file, 'w') as outfile:
                json.dump(self.unmapped_device_details, outfile, indent=4)

            sys.stderr.write(f"\nUnable to generate configurations for all AHUs. "
                             f"Please see {err_file} for details\n")
            sys.exit(1)
        else:
            sys.exit(0)

    def generate_ahu_configs(self, ahu_id):
        final_config = copy.deepcopy(self.config_template)
        ahu = ahu_id.split(".")[-1]
        final_config["device"]["unit"] = {}
        final_config["device"]["unit"][ahu] = {}
        final_config["device"]["unit"][ahu]["subdevices"] = list()
        point_mapping = final_config["arguments"]["point_mapping"]
        missing_points = []
        # Get ahu point details
        for volttron_point_type in self.point_meta_map.keys():
            point_name = self.get_point_name(ahu_id, "ahu", volttron_point_type)
            if point_name:
                point_mapping[volttron_point_type] = point_name
            else:
                missing_points.append(volttron_point_type)

        if missing_points:
            self.unmapped_device_details[ahu_id] = {"type": "ahu",
                                                    "error": f"Unable to find points of type(s): {missing_points}",
                                                    "topic_name": self.equip_id_point_topic_map.get(ahu_id)}
            return ahu, None
        else:
            return ahu, final_config

    @abstractmethod
    def get_point_name(self, equip_id, equip_type, point_key):
        pass
