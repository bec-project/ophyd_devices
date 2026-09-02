"""Module for testing the PSIDeviceBase class."""

import threading
import time
from unittest import mock

import pytest
from bec_server.device_server.devices.devicemanager import DeviceManagerDS
from bec_server.device_server.tests.utils import DMMock
from ophyd import Component as Cpt
from ophyd import Device, Staged
from ophyd.status import StatusBase

from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.sim.sim_camera import SimCamera
from ophyd_devices.sim.sim_positioner import SimPositioner
from ophyd_devices.tests.utils import get_mock_scan_info

# pylint: disable=redefined-outer-name
# pylint: disable=protected-access


class SimPositionerDevice(PSIDeviceBase, SimPositioner):
    """Simulated Positioner Device with PSI Device Base"""


class SimDevice(PSIDeviceBase, Device):
    """Simulated Device with PSI Device Base"""


class ParentDevice(PSIDeviceBase):
    """PSI device with a PSI subdevice."""

    child = Cpt(PSIDeviceBase, "child:")


class NonPSIParentDevice(Device):
    """Plain ophyd device with a PSI subdevice."""

    child = Cpt(PSIDeviceBase, "child:")


class NestedParentDevice(PSIDeviceBase):
    """PSI device with a plain ophyd child that contains a PSI subdevice."""

    container = Cpt(NonPSIParentDevice, "container:")


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


def test_psi_device_base_can_be_created_as_component():
    """Test PSIDeviceBase compatibility with ophyd Component.create_component."""
    parent = ParentDevice("root:", name="parent")

    assert parent.child.name == "parent_child"
    assert parent.child.prefix == "root:child:"
    assert parent.child.parent is parent


def test_psi_subdevice_inherits_bec_context():
    """Test PSI subdevices use the parent's BEC context by default."""
    dm = mock.MagicMock()
    scan_info = mock.MagicMock()
    parent = ParentDevice("root:", name="parent", device_manager=dm, scan_info=scan_info)

    assert parent.child.device_manager is dm
    assert parent.child.scan_info is scan_info


def test_psi_subdevice_under_plain_ophyd_parent_uses_mock_context():
    """Test PSI subdevices outside BEC context keep the top-level mock fallback."""
    parent = NonPSIParentDevice("root:", name="parent")

    assert parent.child.device_manager is None
    assert parent.child.scan_info is not None
    assert parent.child.scan_info is not getattr(parent, "scan_info", None)


def test_psi_subdevice_under_plain_ophyd_parent_can_inherit_explicit_context():
    """Test plain parents can host PSI subdevices when they expose BEC context."""
    dm = mock.MagicMock()
    scan_info = mock.MagicMock()

    class ContextParentDevice(Device):
        child = Cpt(PSIDeviceBase, "child:")

        def __init__(self, *args, **kwargs):
            self.device_manager = dm
            self.scan_info = scan_info
            super().__init__(*args, **kwargs)

    parent = ContextParentDevice("root:", name="parent")

    assert parent.child.device_manager is dm
    assert parent.child.scan_info is scan_info


def test_psi_subdevice_walks_parent_chain_for_bec_context():
    """Test nested PSI subdevices inherit BEC context from higher ancestors."""
    dm = mock.MagicMock()
    scan_info = mock.MagicMock()
    parent = NestedParentDevice("root:", name="parent", device_manager=dm, scan_info=scan_info)

    assert parent.container.child.device_manager is dm
    assert parent.container.child.scan_info is scan_info


def test_psi_subdevice_context_with_bec_device_manager_construction():
    """Test BEC device-manager construction passes context to nested PSI subdevices."""
    dm = DMMock()
    dm.scan_info = get_mock_scan_info(device=None)
    config = {
        "name": "parent",
        "deviceClass": "tests.test_psi_device_base.NestedParentDevice",
        "deviceConfig": {"prefix": "root:"},
    }

    with mock.patch.object(DeviceManagerDS, "_get_device_class", return_value=NestedParentDevice):
        parent, leftover_config = DeviceManagerDS.construct_device_obj(config, dm)

    assert leftover_config == {}
    assert parent.device_manager is dm
    assert parent.scan_info is dm.scan_info
    assert parent.container.child.device_manager is dm
    assert parent.container.child.scan_info is dm.scan_info


def test_psi_subdevice_follows_parent_stage_and_unstage():
    """Test ophyd side-effects when PSIDeviceBase is used as a subdevice."""
    parent = ParentDevice("root:", name="parent")

    assert parent.staged == Staged.no
    assert parent.child.staged == Staged.no

    staged = parent.stage()
    assert staged == [parent, parent.child]
    assert parent.staged == Staged.yes
    assert parent.child.staged == Staged.yes

    unstaged = parent.unstage()
    assert unstaged == [parent.child, parent]
    assert parent.staged == Staged.no
    assert parent.child.staged == Staged.no


def test_psi_subdevice_stop_is_propagated_when_connected():
    """Test parent stop propagates to connected PSI subdevices."""
    parent = ParentDevice("root:", name="parent")

    with mock.patch.object(PSIDeviceBase, "connected", new_callable=mock.PropertyMock) as connected:
        connected.return_value = True
        parent.stop()

    assert parent.stopped is True
    assert parent.child.stopped is True


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
