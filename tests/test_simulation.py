from unittest import mock
import pytest
import numpy as np

from ophyd_devices.utils.bec_device_base import BECDeviceBase, BECDevice
from ophyd_devices.sim.sim import SimMonitor, SimCamera, SimPositioner

from tests.utils import DMMock
from ophyd import Device, Signal


@pytest.fixture(scope="function")
def monitor(name="monitor"):
    """Fixture for SimMonitor."""
    dm = DMMock()
    mon = SimMonitor(name=name, device_manager=dm)
    yield mon


@pytest.fixture(scope="function")
def camera(name="camera"):
    """Fixture for SimCamera."""
    dm = DMMock()
    cam = SimCamera(name=name, device_manager=dm)
    yield cam


@pytest.fixture(scope="function")
def positioner(name="positioner"):
    """Fixture for SimPositioner."""
    dm = DMMock()
    pos = SimPositioner(name=name, device_manager=dm)
    yield pos


def test_monitor__init__(monitor):
    """Test the __init__ method of SimMonitor."""
    assert isinstance(monitor, SimMonitor)
    assert isinstance(monitor, BECDevice)


@pytest.mark.parametrize("center", [-10, 0, 10])
def test_monitor_readback(monitor, center):
    """Test the readback method of SimMonitor."""
    for model_name in monitor.sim.sim_get_models():
        monitor.sim.sim_select_model(model_name)
        monitor.sim.sim_params["noise_multipler"] = 10
        if "c" in monitor.sim.sim_params:
            monitor.sim.sim_params["c"] = center
        elif "center" in monitor.sim.sim_params:
            monitor.sim.sim_params["center"] = center
        assert isinstance(monitor.read()[monitor.name]["value"], monitor.BIT_DEPTH)
        expected_value = monitor.sim._model.eval(monitor.sim._model_params, x=0)
        print(expected_value, monitor.read()[monitor.name]["value"])
        tolerance = (
            monitor.sim.sim_params["noise_multipler"] + 1
        )  # due to ceiling in calculation, but maximum +1int
        assert np.isclose(
            monitor.read()[monitor.name]["value"],
            expected_value,
            atol=monitor.sim.sim_params["noise_multipler"] + 1,
        )


def test_camera__init__(camera):
    """Test the __init__ method of SimMonitor."""
    assert isinstance(camera, SimCamera)
    assert isinstance(camera, BECDevice)


@pytest.mark.parametrize("amplitude, noise_multiplier", [(0, 1), (100, 10), (1000, 50)])
def test_camera_readback(camera, amplitude, noise_multiplier):
    """Test the readback method of SimMonitor."""
    for model_name in camera.sim.sim_get_models():
        camera.sim.sim_select_model(model_name)
        camera.sim.sim_params = {"noise_multiplier": noise_multiplier}
        camera.sim.sim_params = {"amplitude": amplitude}
        camera.sim.sim_params = {"noise": "poisson"}
        assert camera.image.get().shape == camera.SHAPE
        assert isinstance(camera.image.get()[0, 0], camera.BIT_DEPTH)
        camera.sim.sim_params = {"noise": "uniform"}
        camera.sim.sim_params = {"hot_pixel_coords": []}
        camera.sim.sim_params = {"hot_pixel_values": []}
        camera.sim.sim_params = {"hot_pixel_types": []}
        assert camera.image.get().shape == camera.SHAPE
        assert isinstance(camera.image.get()[0, 0], camera.BIT_DEPTH)
        assert (camera.image.get() <= (amplitude + noise_multiplier + 1)).all()


def test_positioner__init__(positioner):
    """Test the __init__ method of SimPositioner."""
    assert isinstance(positioner, SimPositioner)
    assert isinstance(positioner, BECDevice)


def test_positioner_move(positioner):
    """Test the move method of SimPositioner."""
    positioner.move(0).wait()
    assert np.isclose(positioner.read()[positioner.name]["value"], 0, atol=positioner.tolerance)
    positioner.move(10).wait()
    assert np.isclose(positioner.read()[positioner.name]["value"], 10, atol=positioner.tolerance)


@pytest.mark.parametrize("proxy_active", [True, False])
def test_sim_camera_proxies(camera, proxy_active):
    """Test mocking compute_method with framework class"""
    camera.device_manager.add_device("test_proxy")
    if proxy_active:
        camera._registered_proxies["test_proxy"] = camera.image.name
    else:
        camera._registered_proxies = {}
    proxy = camera.device_manager.devices["test_proxy"]
    mock_method = mock.MagicMock()
    mock_obj = proxy.obj
    mock_obj.lookup = mock.MagicMock()
    mock_obj.lookup.return_value = {camera.name: {"method": mock_method, "args": 1, "kwargs": 1}}
    camera.image.read()
    if proxy_active:
        assert len(mock_obj.lookup.mock_calls) > 0
    elif not proxy_active:
        assert len(mock_obj.lookup.mock_calls) == 0


def test_BECDeviceBase():
    # Test the BECDeviceBase class
    bec_device_base = BECDeviceBase(name="test")
    assert isinstance(bec_device_base, BECDevice)
    assert bec_device_base.connected is True
    signal = Signal(name="signal")
    assert isinstance(signal, BECDevice)
    device = Device(name="device")
    assert isinstance(device, BECDevice)
