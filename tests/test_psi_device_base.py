"""Module for testing the PSIDeviceBase class."""

from unittest import mock

import pytest
from ophyd import Device
from ophyd.status import StatusBase

from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.sim.sim_camera import SimCamera
from ophyd_devices.sim.sim_positioner import SimPositioner

# pylint: disable=redefined-outer-name
# pylint: disable=protected-access


class SimPositionerDevice(PSIDeviceBase, SimPositioner):
    """Simulated Positioner Device with PSI Device Base"""


class SimDevice(PSIDeviceBase, Device):
    """Simulated Device with PSI Device Base"""


@pytest.fixture
def device_positioner():
    """Fixture for Device"""
    yield SimPositionerDevice(name="device")


@pytest.fixture
def device():
    """Fixture for Device"""
    yield SimDevice(name="device", prefix="test:")


def test_psi_device_base_wait_for_signals(device_positioner):
    """Test wait_for_signals method"""
    device: SimPositionerDevice = device_positioner
    device.motor_is_moving.set(1).wait()

    def check_motor_is_moving():
        return device.motor_is_moving.get() == 0

    # Timeout
    assert device.wait_for_condition(check_motor_is_moving, timeout=0.2) is False

    # Stopped
    device._stopped = True
    with pytest.raises(DeviceStoppedError):
        device.wait_for_condition(check_motor_is_moving, timeout=1, check_stopped=True)

    # Success
    device._stopped = False
    device.motor_is_moving.set(0).wait()
    assert device.wait_for_condition(check_motor_is_moving, timeout=1, check_stopped=True) is True

    device.velocity.set(10).wait()

    def check_both_conditions():
        return device.motor_is_moving.get() == 0 and device.velocity.get() == 10

    # All signals True, default
    assert device.wait_for_condition(check_both_conditions, timeout=1) is True

    def check_any_conditions():
        return device.motor_is_moving.get() == 0 or device.velocity.get() == 10

    # Any signal is True
    assert device.wait_for_condition(check_any_conditions, timeout=1) is True


def test_psi_device_base_init_with_device_manager():
    """Test init with device manager"""
    dm = mock.MagicMock()
    device = SimPositionerDevice(name="device", device_manager=dm)
    assert device.device_manager is dm
    # device_manager should b passed to SimCamera through PSIDeviceBase
    device_2 = SimCamera(name="device", device_manager=dm)
    assert device_2.device_manager is dm


def test_on_stage_hook(device):
    """Test user method hooks"""
    with mock.patch.object(device, "on_stage") as mock_on_stage:
        res = device.stage()
        if not isinstance(res, StatusBase):
            assert isinstance(res, list) is True
        mock_on_stage.assert_called_once()


def test_on_unstage_hook(device):
    """Test user method hooks"""
    with mock.patch.object(device, "on_unstage") as mock_on_unstage:
        res = device.unstage()
        if not isinstance(res, StatusBase):
            assert isinstance(res, list) is True
        mock_on_unstage.assert_called_once()


def test_on_complete_hook(device):
    """Test user method hooks"""
    with mock.patch.object(device, "on_complete") as mock_on_complete:
        status = device.complete()
        assert isinstance(status, StatusBase) is True
        mock_on_complete.assert_called_once()


def test_on_kickoff_hook(device):
    """Test user method hooks"""
    with mock.patch.object(device, "on_kickoff") as mock_on_kickoff:
        status = device.kickoff()
        assert isinstance(status, StatusBase) is True
        mock_on_kickoff.assert_called_once()


def test_on_trigger_hook(device):
    """Test user method hooks"""
    with mock.patch.object(device, "on_trigger") as mock_on_trigger:
        mock_on_trigger.return_value = None
        status = device.trigger()
        assert isinstance(status, StatusBase) is True
        mock_on_trigger.assert_called_once()


def test_on_pre_scan_hook(device):
    """Test user method hooks"""
    with mock.patch.object(device, "on_pre_scan") as mock_on_pre_scan:
        mock_on_pre_scan.return_value = None
        status = device.pre_scan()
        assert status is None
        mock_on_pre_scan.assert_called_once()


def test_on_stop_hook(device):
    """Test user method hooks"""
    with mock.patch.object(device, "on_stop") as mock_on_stop:
        device.stop()
        mock_on_stop.assert_called_once()
