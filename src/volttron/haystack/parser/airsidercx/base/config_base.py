import json
import os.path
from abc import abstractmethod
import re

_comment_re = re.compile(
    r'((["\'])(?:\\?.)*?\2)|(/\*.*?\*/)|((?:#|//).*?(?=\n|$))',
    re.MULTILINE | re.DOTALL)


# TODO - get ILC details and pull AirsideRCxConfigGenerator and
#  into 1 base class DriverConfigGenerator
class AirsideRCxConfigGenerator:
    """
    Base class that parses haystack tags to generate
    AirsideRCx agent configuration based on a configuration template
    """

    def __init__(self, config):
        if isinstance(config, dict):
            self.config_dict = config
        else:
            try:
                with open(config, "r") as f:
                    self.config_dict = json.loads(self.strip_comments(f.read()))
            except Exception:
                raise

        self.site_id = self.config_dict.get("site_id", "")
        self.building = self.config_dict.get("building")
        self.campus = self.config_dict.get("campus")
        if not self.building and self.site_id:
            self.building = self.site_id.split(".")[-1]
        if not self.campus and self.site_id:
            self.campus = self.site_id.split(".")[-2]

        # topic_prefix = self.config_dict.get("topic_prefix")
        # if not topic_prefix:
        #     topic_prefix = "devices"
        #     if self.campus:
        #         topic_prefix = topic_prefix + f"/{self.campus}"
        #     if self.building:
        #         topic_prefix = topic_prefix + f"/{self.building}"
        #
        # if not topic_prefix.endswith("/"):
        #     topic_prefix = topic_prefix + "/"
        # self.ahu_topic_pattern = topic_prefix + "{}"
        # self.vav_topic_pattern = topic_prefix + "{}/{}"

        self.config_template = self.config_dict.get("config_template")
        self.config_template["device"] = {
            "campus": self.campus,
            "building": self.building,
            "unit": {}
        }
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
        print(f"Got ahu and vavs as {result}")
        if isinstance(result, dict):
            iterator = result.items()
        else:
            iterator = result
        for ahu_id, vavs in iterator:
            ahu_name, result_dict = self.generate_ahu_configs(ahu_id, vavs)

            with open(f"{self.output_dir}/{ahu_name}.json", 'w') as outfile:
                json.dump(result_dict, outfile, indent=4)

    @abstractmethod
    def generate_ahu_configs(self, ahu_id, vavs):
        pass

    def _repl(self, match):
        """Replace the matched group with an appropriate string."""
        # If the first group matched, a quoted string was matched and should
        # be returned unchanged.  Otherwise a comment was matched and the
        # empty string should be returned.
        return match.group(1) or ''

    def strip_comments(self, string):
        """Return string with all comments stripped.

        Both JavaScript-style comments (//... and /*...*/) and hash (#...)
        comments are removed.
        """
        return _comment_re.sub(self._repl, string)
