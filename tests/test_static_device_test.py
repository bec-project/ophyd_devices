import os
import sys

import bec_lib

from ophyd_devices.utils.static_device_test import launch


def test_static_device_test():
    config_path = os.path.join(os.path.dirname(bec_lib.__file__), "configs", "demo_config.yaml")
    sys.argv = ["", "--config", config_path, "--connect"]
    launch()
