"""Module for testing the PSIDeviceBase class."""

import threading
import time
from unittest import mock

import pytest
from ophyd import Component as Cpt
from ophyd import Device, Signal
from ophyd.status import StatusBase

from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.sim.sim_camera import SimCamera
from ophyd_devices.sim.sim_positioner import SimPositioner
from ophyd_devices.utils.psi_device_base_utils import DeviceStatus as PSIDeviceStatus
from ophyd_devices.utils.psi_device_base_utils import MoveStatus as PSIMoveStatus
from ophyd_devices.utils.psi_device_base_utils import StatusBase as PSIStatusBase
from ophyd_devices.utils.psi_device_base_utils import (
    StatusTimeoutErrorWithErrorInfo,
    SubscriptionStatus,
)

# pylint: disable=redefined-outer-name
# pylint: disable=protected-access


class SimPositionerDevice(PSIDeviceBase, SimPositioner):
    """Simulated Positioner Device with PSI Device Base"""


class SimDevice(PSIDeviceBase, Device):
    """Simulated Device with PSI Device Base"""


class TimeoutConfiguredDevice(PSIDeviceBase, Device):
    """Simulated device with a default timeout for status objects."""

    DEFAULT_STATUS_TIMEOUT = 0.5
    signal = Cpt(Signal, value=0)


class TimeoutConfiguredPositionerDevice(PSIDeviceBase, SimPositioner):
    """Simulated positioner device with a default timeout for move statuses."""

    DEFAULT_STATUS_TIMEOUT = 0.5


@pytest.fixture
def device_positioner():
    """Fixture for Device"""
    yield SimPositionerDevice(name="device")


@pytest.fixture
def device():
    """Fixture for Device"""
    yield SimDevice(name="device", prefix="test:")


@pytest.fixture
def timeout_device():
    """Fixture for a device with default status timeout configuration."""
    yield TimeoutConfiguredDevice(name="timeout_device", prefix="test:")


@pytest.fixture
def timeout_positioner():
    """Fixture for a positioner device with default status timeout configuration."""
    yield TimeoutConfiguredPositionerDevice(name="timeout_positioner")


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


def test_device_default_status_timeout_applies_to_status_objects(timeout_device):
    """Status objects should inherit the owning device's default timeout."""
    status = PSIStatusBase(obj=timeout_device)
    device_status = PSIDeviceStatus(timeout_device)
    subscription_status = SubscriptionStatus(
        timeout_device.signal, callback=lambda *args, **kwargs: False, run=False
    )

    assert status.timeout == timeout_device.DEFAULT_STATUS_TIMEOUT
    assert device_status.timeout == timeout_device.DEFAULT_STATUS_TIMEOUT
    assert subscription_status.timeout == timeout_device.DEFAULT_STATUS_TIMEOUT


def test_subscription_status_with_default_timeout_normalizes_none_settle_time(timeout_device):
    """SubscriptionStatus should safely normalize None settle_time when a default timeout applies."""
    status = SubscriptionStatus(
        timeout_device.signal, callback=lambda *args, **kwargs: False, run=False
    )

    assert status.settle_time == 0.0

    with pytest.raises(StatusTimeoutErrorWithErrorInfo):
        status.wait(timeout=1)


def test_device_default_status_timeout_can_be_overridden(timeout_device):
    """Explicit timeouts should take precedence over the device default."""
    status = PSIStatusBase(obj=timeout_device, timeout=1.25)
    device_status = PSIDeviceStatus(timeout_device, timeout=1.5)

    assert status.timeout == 1.25
    assert device_status.timeout == 1.5


def test_psidevicebase_fallback_statuses_use_default_timeout(timeout_device):
    """Base-class fallback kickoff/complete statuses should use the device default timeout."""
    kickoff_status = timeout_device.kickoff()
    complete_status = timeout_device.complete()

    assert kickoff_status.timeout == timeout_device.DEFAULT_STATUS_TIMEOUT
    assert complete_status.timeout == timeout_device.DEFAULT_STATUS_TIMEOUT


def test_move_status_uses_device_default_timeout(timeout_positioner):
    """Move statuses should inherit the default timeout from PSI positioner devices."""
    status = PSIMoveStatus(timeout_positioner, target=1)
    assert status.timeout == timeout_positioner.DEFAULT_STATUS_TIMEOUT
