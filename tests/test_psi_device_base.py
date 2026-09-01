"""Module for testing the PSIDeviceBase class."""

import threading
import time
from unittest import mock

import numpy as np
import pytest
from ophyd import Component as Cpt
from ophyd import Device, Signal
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


class TimeoutSignalDevice(PSIDeviceBase, Device):
    """Device that exposes the base timeout as a signal."""

    timeout = Cpt(Signal, value=10)

    def __init__(self, timeout=10, **kwargs):
        super().__init__(timeout=timeout, **kwargs)
        self.timeout.subscribe(self._on_timeout_change, run=False)

    def _on_timeout_change(self, value, **kwargs):
        self._timeout = self._normalize_timeout(value)


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


def test_psi_device_base_timeout_init_arg():
    """Test default timeout initialization."""
    assert SimDevice(name="device")._timeout is None
    assert SimDevice(name="device", timeout=3)._timeout == 3
    assert SimDevice(name="device", timeout=0)._timeout is None
    assert SimDevice(name="device", timeout=-5)._timeout is None
    assert SimDevice(name="device", timeout=float("nan"))._timeout is None
    assert SimDevice(name="device", timeout=float("inf"))._timeout is None
    assert SimDevice(name="device", timeout=np.int64(3))._timeout == 3.0
    assert SimDevice(name="device", timeout=np.float32(3))._timeout == 3.0
    with pytest.raises(TypeError):
        SimDevice(name="device", timeout=True)
    with pytest.raises(TypeError):
        SimDevice(name="device", timeout="3")


def test_psi_device_base_timeout_signal_compatibility():
    """Test that subclasses can expose timeout as a signal."""
    device = TimeoutSignalDevice(name="device")

    assert device._timeout == 10
    assert device.timeout.get() == 10

    device.timeout.set(5).wait()
    assert device._timeout == 5

    device.timeout.set(0).wait()
    assert device.timeout.get() == 0
    assert device._timeout is None


def test_psi_device_base_fallback_statuses_use_default_timeout():
    """Test fallback complete and kickoff statuses use the base timeout."""
    device = SimDevice(name="device", timeout=3)

    assert device.complete().timeout == 3
    assert device.kickoff().timeout == 3


def test_on_stage_hook(device):
    """Test user method hooks"""
    with mock.patch.object(device, "on_stage") as mock_on_stage:
        res = device.stage()
        if not isinstance(res, StatusBase):
            assert isinstance(res, list) is True
        mock_on_stage.assert_called_once()


def test_on_destroy_hook(device):
    """Test on destroy hook"""
    assert device.destroyed is False
    with mock.patch.object(device, "on_destroy") as mock_on_destroy:
        device.destroy()
        mock_on_destroy.assert_called_once()
        assert device.destroyed is True


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


def test_stoppable_status(device):
    """Test stoppable status"""
    status = StatusBase()
    device.cancel_on_stop(status)
    device.stop()
    assert status.done is True
    assert status.success is False


def test_stoppable_status_not_done(device):
    """Test stoppable status not done"""

    def stop_after_delay():
        time.sleep(5)
        device.stop()

    status = StatusBase()
    device.cancel_on_stop(status)
    thread = threading.Thread(target=stop_after_delay)
    thread.start()

    with pytest.raises(DeviceStoppedError, match="Device device has been stopped"):
        status.wait()

    assert status.done is True
    assert status.success is False
