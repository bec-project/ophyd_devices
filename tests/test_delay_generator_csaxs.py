# pylint: skip-file
from unittest import mock

import pytest

from ophyd_devices.epics.devices.delay_generator_csaxs import DDGSetup
from ophyd_devices.epics.devices.psi_delay_generator_base import TriggerSource


def patch_dual_pvs(device):
    for walk in device.walk_signals():
        if not hasattr(walk.item, "_read_pv"):
            continue
        if not hasattr(walk.item, "_write_pv"):
            continue
        if walk.item._read_pv.pvname.endswith("_RBV"):
            walk.item._read_pv = walk.item._write_pv


@pytest.fixture(scope="function")
def mock_DDGSetup():
    mock_ddg = mock.MagicMock()
    yield DDGSetup(parent=mock_ddg)


# Fixture for scaninfo
@pytest.fixture(
    params=[
        {
            "scan_id": "1234",
            "scan_type": "step",
            "num_points": 500,
            "frames_per_trigger": 1,
            "exp_time": 0.1,
            "readout_time": 0.1,
        },
        {
            "scan_id": "1234",
            "scan_type": "step",
            "num_points": 500,
            "frames_per_trigger": 5,
            "exp_time": 0.01,
            "readout_time": 0,
        },
        {
            "scan_id": "1234",
            "scan_type": "fly",
            "num_points": 500,
            "frames_per_trigger": 1,
            "exp_time": 1,
            "readout_time": 0.2,
        },
        {
            "scan_id": "1234",
            "scan_type": "fly",
            "num_points": 500,
            "frames_per_trigger": 5,
            "exp_time": 0.1,
            "readout_time": 0.4,
        },
    ]
)
def scaninfo(request):
    return request.param


# Fixture for DDG config default values
@pytest.fixture(
    params=[
        {
            "delay_burst": 0.0,
            "delta_width": 0.0,
            "additional_triggers": 0,
            "polarity": [0, 0, 0, 0, 0],
            "amplitude": 0.0,
            "offset": 0.0,
            "thres_trig_level": 0.0,
        },
        {
            "delay_burst": 0.1,
            "delta_width": 0.1,
            "additional_triggers": 1,
            "polarity": [0, 0, 1, 0, 0],
            "amplitude": 5,
            "offset": 0.0,
            "thres_trig_level": 2.5,
        },
    ]
)
def ddg_config_defaults(request):
    return request.param


# Fixture for DDG config scan values
@pytest.fixture(
    params=[
        {
            "fixed_ttl_width": [0, 0, 0, 0, 0],
            "trigger_width": None,
            "set_high_on_exposure": False,
            "set_high_on_stage": False,
            "set_trigger_source": "SINGLE_SHOT",
            "premove_trigger": False,
        },
        {
            "fixed_ttl_width": [0, 0, 0, 0, 0],
            "trigger_width": 0.1,
            "set_high_on_exposure": True,
            "set_high_on_stage": False,
            "set_trigger_source": "SINGLE_SHOT",
            "premove_trigger": True,
        },
        {
            "fixed_ttl_width": [0, 0, 0, 0, 0],
            "trigger_width": 0.1,
            "set_high_on_exposure": False,
            "set_high_on_stage": False,
            "set_trigger_source": "EXT_RISING_EDGE",
            "premove_trigger": False,
        },
    ]
)
def ddg_config_scan(request):
    return request.param


# Fixture for delay pairs
@pytest.fixture(
    params=[
        {"all_channels": ["channelAB", "channelCD"], "all_delay_pairs": ["AB", "CD"]},
        {"all_channels": [], "all_delay_pairs": []},
        {"all_channels": ["channelT0", "channelAB", "channelCD"], "all_delay_pairs": ["AB", "CD"]},
    ]
)
def channel_pairs(request):
    return request.param


def test_check_scan_id(mock_DDGSetup, scaninfo, ddg_config_defaults, ddg_config_scan):
    """Test the check_scan_id method."""
    # Set first attributes of parent class
    for k, v in scaninfo.items():
        setattr(mock_DDGSetup.parent.scaninfo, k, v)
    for k, v in ddg_config_defaults.items():
        getattr(mock_DDGSetup.parent, k).get.return_value = v
    for k, v in ddg_config_scan.items():
        getattr(mock_DDGSetup.parent, k).get.return_value = v
    # Call the function you want to test
    mock_DDGSetup.check_scan_id()
    mock_DDGSetup.parent.scaninfo.load_scan_metadata.assert_called_once()


def test_on_pre_scan(mock_DDGSetup, scaninfo, ddg_config_defaults, ddg_config_scan):
    """Test the check_scan_id method."""
    # Set first attributes of parent class
    for k, v in scaninfo.items():
        setattr(mock_DDGSetup.parent.scaninfo, k, v)
    for k, v in ddg_config_defaults.items():
        getattr(mock_DDGSetup.parent, k).get.return_value = v
    for k, v in ddg_config_scan.items():
        getattr(mock_DDGSetup.parent, k).get.return_value = v
    # Call the function you want to test
    mock_DDGSetup.on_pre_scan()
    if ddg_config_scan["premove_trigger"]:
        mock_DDGSetup.parent.trigger_shot.put.assert_called_once_with(1)


@pytest.mark.parametrize("source", ["SINGLE_SHOT", "EXT_RISING_EDGE"])
def test_on_trigger(mock_DDGSetup, scaninfo, ddg_config_defaults, ddg_config_scan, source):
    """Test the on_trigger method."""
    # Set first attributes of parent class
    for k, v in scaninfo.items():
        setattr(mock_DDGSetup.parent.scaninfo, k, v)
    for k, v in ddg_config_defaults.items():
        getattr(mock_DDGSetup.parent, k).get.return_value = v
    for k, v in ddg_config_scan.items():
        getattr(mock_DDGSetup.parent, k).get.return_value = v
    # Call the function you want to test
    mock_DDGSetup.parent.source.name = "source"
    mock_DDGSetup.parent.source.read.return_value = {
        mock_DDGSetup.parent.source.name: {"value": getattr(TriggerSource, source)}
    }
    mock_DDGSetup.on_trigger()
    if source == "SINGLE_SHOT":
        mock_DDGSetup.parent.trigger_shot.put.assert_called_once_with(1)


def test_initialize_default_parameter(
    mock_DDGSetup, scaninfo, ddg_config_defaults, ddg_config_scan, channel_pairs
):
    """Test the initialize_default_parameter method."""
    # Set first attributes of parent class
    for k, v in scaninfo.items():
        setattr(mock_DDGSetup.parent.scaninfo, k, v)
    for k, v in ddg_config_defaults.items():
        getattr(mock_DDGSetup.parent, k).get.return_value = v
    for k, v in ddg_config_scan.items():
        getattr(mock_DDGSetup.parent, k).get.return_value = v
    # Call the function you want to test
    mock_DDGSetup.parent.all_channels = channel_pairs["all_channels"]
    mock_DDGSetup.parent.all_delay_pairs = channel_pairs["all_delay_pairs"]
    calls = []
    calls.extend(
        [
            mock.call("polarity", ddg_config_defaults["polarity"][ii], [channel])
            for ii, channel in enumerate(channel_pairs["all_channels"])
        ]
    )
    calls.extend([mock.call("amplitude", ddg_config_defaults["amplitude"])])
    calls.extend([mock.call("offset", ddg_config_defaults["offset"])])
    calls.extend(
        [
            mock.call(
                "reference", 0, [f"channel{pair}.ch1" for pair in channel_pairs["all_delay_pairs"]]
            )
        ]
    )
    calls.extend(
        [
            mock.call(
                "reference", 0, [f"channel{pair}.ch2" for pair in channel_pairs["all_delay_pairs"]]
            )
        ]
    )
    mock_DDGSetup.initialize_default_parameter()
    mock_DDGSetup.parent.set_channels.assert_has_calls(calls)


def test_prepare_ddg(mock_DDGSetup, scaninfo, ddg_config_defaults, ddg_config_scan, channel_pairs):
    """Test the prepare_ddg method."""
    # Set first attributes of parent class
    for k, v in scaninfo.items():
        setattr(mock_DDGSetup.parent.scaninfo, k, v)
    for k, v in ddg_config_defaults.items():
        getattr(mock_DDGSetup.parent, k).get.return_value = v
    for k, v in ddg_config_scan.items():
        getattr(mock_DDGSetup.parent, k).get.return_value = v
    # Call the function you want to test
    mock_DDGSetup.parent.all_channels = channel_pairs["all_channels"]
    mock_DDGSetup.parent.all_delay_pairs = channel_pairs["all_delay_pairs"]

    mock_DDGSetup.prepare_ddg()
    mock_DDGSetup.parent.set_trigger.assert_called_once_with(
        getattr(TriggerSource, ddg_config_scan["set_trigger_source"])
    )
    if scaninfo["scan_type"] == "step":
        if ddg_config_scan["set_high_on_exposure"]:
            num_burst_cycle = 1 + ddg_config_defaults["additional_triggers"]
            exp_time = ddg_config_defaults["delta_width"] + scaninfo["frames_per_trigger"] * (
                scaninfo["exp_time"] + scaninfo["readout_time"]
            )
            total_exposure = exp_time
            delay_burst = ddg_config_defaults["delay_burst"]
        else:
            exp_time = ddg_config_defaults["delta_width"] + scaninfo["exp_time"]
            total_exposure = exp_time + scaninfo["readout_time"]
            delay_burst = ddg_config_defaults["delay_burst"]
            num_burst_cycle = (
                scaninfo["frames_per_trigger"] + ddg_config_defaults["additional_triggers"]
            )
    elif scaninfo["scan_type"] == "fly":
        if ddg_config_scan["set_high_on_exposure"]:
            num_burst_cycle = 1 + ddg_config_defaults["additional_triggers"]
            exp_time = (
                ddg_config_defaults["delta_width"]
                + scaninfo["num_points"] * scaninfo["exp_time"]
                + (scaninfo["num_points"] - 1) * scaninfo["readout_time"]
            )
            total_exposure = exp_time
            delay_burst = ddg_config_defaults["delay_burst"]
        else:
            exp_time = ddg_config_defaults["delta_width"] + scaninfo["exp_time"]
            total_exposure = exp_time + scaninfo["readout_time"]
            delay_burst = ddg_config_defaults["delay_burst"]
            num_burst_cycle = scaninfo["num_points"] + ddg_config_defaults["additional_triggers"]

    # mock_DDGSetup.parent.burst_enable.assert_called_once_with(
    #     mock.call(num_burst_cycle, delay_burst, total_exposure, config="first")
    # )
    mock_DDGSetup.parent.burst_enable.assert_called_once_with(
        num_burst_cycle, delay_burst, total_exposure, config="first"
    )
    if not ddg_config_scan["trigger_width"]:
        call = mock.call("width", exp_time)
        assert call in mock_DDGSetup.parent.set_channels.mock_calls
    else:
        call = mock.call("width", ddg_config_scan["trigger_width"])
        assert call in mock_DDGSetup.parent.set_channels.mock_calls
    if ddg_config_scan["set_high_on_exposure"]:
        calls = [
            mock.call("width", value, channels=[channel])
            for value, channel in zip(
                ddg_config_scan["fixed_ttl_width"], channel_pairs["all_channels"]
            )
            if value != 0
        ]
        if calls:
            assert all(calls in mock_DDGSetup.parent.set_channels.mock_calls)
