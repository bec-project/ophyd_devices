import os
import sys
from unittest import mock

import bec_lib

from ophyd_devices.utils.static_device_test import StaticDeviceTest, TestResult, launch


def test_static_device_test():
    config_path = os.path.join(os.path.dirname(bec_lib.__file__), "configs", "demo_config.yaml")
    sys.argv = ["", "--config", config_path, "--connect"]
    launch()


def test_static_device_test_with_config_dict():
    """First device is okay, second one is not"""
    device_dict = {
        "waveform": {
            "readoutPriority": "async",
            "deviceClass": "ophyd_devices.SimWaveform",
            "deviceConfig": {
                "waveform_shape": 1000,
                "sim_init": {
                    "model": "GaussianModel",
                    "params": {"amplitude": 100, "center": 500, "sigma": 50},
                },
            },
            "deviceTags": ["detector"],
            "enabled": True,
            "readOnly": False,
            "softwareTrigger": True,
        },
        "wrong": {"this is not corect": 0},
    }
    test = StaticDeviceTest(config_dict=device_dict)
    ret = test.run_with_list_output(connect=False)
    assert len(ret) == 2
    assert ret[0].name == "waveform"
    assert ret[0].success is True
    assert ret[0].message == "waveform is OK"
    assert ret[1].name == "wrong"
    assert ret[1].success is False
    assert isinstance(ret[1].message, str)


def test_static_device_test_TestResults():
    result = TestResult(
        name="test_device", success=True, message="Device is OK", config_is_valid=True
    )
    assert result.name == "test_device"
    assert result.success is True
    assert result.message == "Device is OK"
    assert result.config_is_valid is True
