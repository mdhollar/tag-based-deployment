import json
import os.path
from abc import abstractmethod
from volttron.haystack.parser.utils import strip_comments


class DriverConfigGenerator:
    """
    Base class that parses haystack tags to generate
    platform driver configuration based on a configuration template
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
            self.building = self.get_name_from_id(self.site_id)
        if not self.campus and self.site_id:
            self.campus = self.site_id.split(".")[-2]

        topic_prefix = self.config_dict.get("topic_prefix")
        if not topic_prefix:
            topic_prefix = "devices"
            if self.campus:
                topic_prefix = topic_prefix + f"/{self.campus}"
            if self.building:
                topic_prefix = topic_prefix + f"/{self.building}"

        if not topic_prefix.endswith("/"):
            topic_prefix = topic_prefix + "/"
        self.ahu_topic_pattern = topic_prefix + "{}"
        self.vav_topic_pattern = topic_prefix + "{ahu}/{vav}"

        self.config_template = self.config_dict.get("config_template")

        # initialize output dir
        default_prefix = self.building + "_" if self.building else ""
        self.output_dir = self.config_dict.get(
            "output_dir", f"{default_prefix}driver_configs")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
        elif not os.path.isdir(self.output_dir):
            raise ValueError(f"Output directory {self.output_dir} "
                             f"does not exist")
        print(f"Output directory {os.path.abspath(self.output_dir)}")

    @abstractmethod
    def get_ahu_and_vavs(self):
        """
        Should return a list of ahu and vav mappings
        :return: list of tuples with the format [(ahu1, (vav1,vav2..)),...]
                 or dict mapping ahu with vavs with format
                 {'ahu1':(vav1,vav2,..), ...}
        """
        pass

    def generate_configs(self):
        result = self.get_ahu_and_vavs()
        if isinstance(result, dict):
            iterator = result.items()
        else:
            iterator = result
        for ahu_id, vavs in iterator:
            ahu_name, result_dict = self.generate_ahu_configs(ahu_id, vavs)
            if ahu_name:
                with open(f"{self.output_dir}/{ahu_name}.json", 'w') as outfile:
                    json.dump(result_dict, outfile, indent=4)
            else:
                with open(f"{self.output_dir}/unmapped_vavs.json", 'w') as outfile:
                    json.dump(result_dict, outfile, indent=4)

    def generate_ahu_configs(self, ahu_id, vavs):
        final_mapper = dict()
        ahu = ""
        ahu = self.get_name_from_id(ahu_id)
        # First create the config for the ahu
        topic = self.ahu_topic_pattern.format(ahu)
        if ahu_id:
            # replace right variables in driver_config_template
            final_mapper[topic] = self.generate_config_from_template(ahu_id, "ahu")
            topic_pattern = self.vav_topic_pattern.format(ahu=ahu, vav='{vav}') #fill ahu, leave vav variable
        else:
            topic_pattern = self.vav_topic_pattern.replace("{ahu}/", "")  # ahu
        # Now loop through and do the same for all vavs
        for vav_id in vavs:
            vav = self.get_name_from_id(vav_id)
            topic = topic_pattern.format(vav=vav)
            # replace right variables in driver_config_template
            final_mapper[topic] = self.generate_config_from_template(vav_id, "vav")
        return ahu, final_mapper

    @abstractmethod
    def generate_config_from_template(self, equip_id, equip_type):
        pass

    @abstractmethod
    def get_name_from_id(self, id):
        pass
