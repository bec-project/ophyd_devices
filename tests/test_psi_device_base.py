"""Module for testing the PSIDeviceBase class."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest
from bec_server.device_server.devices.devicemanager import DeviceManagerDS
from bec_server.device_server.tests.utils import DMMock
from ophyd import Component as Cpt
from ophyd import Device, Staged
from ophyd.status import StatusBase

from ophyd_devices.interfaces.base_classes.camera_base import CameraBase
from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.sim.sim_camera import SimCamera
from ophyd_devices.sim.sim_positioner import SimPositioner
from ophyd_devices.tests.utils import get_mock_scan_info
from ophyd_devices.utils.bec_signals import FileEventSignal, PreviewSignal, ProgressSignal
from ophyd_devices.utils.psi_device_base_utils import destroy_subdevices

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


class ChildWithFileEvent(PSIDeviceBase):
    """PSI child with a root-scoped file event signal."""

    file_event = Cpt(FileEventSignal)


class ParentWithDuplicateFileEvent(PSIDeviceBase):
    """PSI parent and child with duplicate root-scoped file event signals."""

    file_event = Cpt(FileEventSignal)
    child = Cpt(ChildWithFileEvent, "child:")


class ChildWithProgress(PSIDeviceBase):
    """PSI child with a root-scoped progress signal."""

    progress = Cpt(ProgressSignal, name="progress")


class ParentWithDuplicateProgress(PSIDeviceBase):
    """PSI parent and child with duplicate root-scoped progress signals."""

    progress = Cpt(ProgressSignal, name="progress")
    child = Cpt(ChildWithProgress, "child:")


class ChildWithPreview(PSIDeviceBase):
    """PSI child with a named preview signal."""

    preview = Cpt(PreviewSignal, name="preview", ndim=1)


class ParentWithMultiplePreviews(PSIDeviceBase):
    """PSI parent and child with multiple non-singleton preview signals."""

    preview = Cpt(PreviewSignal, name="preview", ndim=1)
    child = Cpt(ChildWithPreview, "child:")


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


def test_root_resolved_file_event_signal_is_unique_per_device_tree():
    """Test duplicate root-scoped file event signals fail at construction time."""
    with pytest.raises(RuntimeError, match="root-resolved BEC signal 'file_event'"):
        ParentWithDuplicateFileEvent("root:", name="parent")


def test_root_resolved_progress_signal_is_unique_per_device_tree():
    """Test duplicate root-scoped progress signals fail at construction time."""
    with pytest.raises(RuntimeError, match="root-resolved BEC signal 'progress'"):
        ParentWithDuplicateProgress("root:", name="parent")


def test_duplicate_root_resolved_signal_fails_with_bec_device_manager_construction():
    """Test BEC construction rejects duplicate root-scoped BEC signals."""
    dm = DMMock()
    dm.scan_info = get_mock_scan_info(device=None)
    config = {
        "name": "parent",
        "deviceClass": "tests.test_psi_device_base.ParentWithDuplicateFileEvent",
        "deviceConfig": {"prefix": "root:"},
    }

    with (
        mock.patch.object(
            DeviceManagerDS, "_get_device_class", return_value=ParentWithDuplicateFileEvent
        ),
        pytest.raises(RuntimeError, match="root-resolved BEC signal 'file_event'"),
    ):
        DeviceManagerDS.construct_device_obj(config, dm)


def test_multiple_previews_are_allowed_in_one_device_tree():
    """Test non-singleton BEC signals can appear multiple times when named."""
    parent = ParentWithMultiplePreviews("root:", name="parent")

    assert parent.preview.parent is parent
    assert parent.child.preview.parent is parent.child


def test_root_resolved_signal_registry_is_stored_on_root_device():
    """Test root-resolved BEC signal ownership is tracked on the root instance."""
    parent = ChildWithFileEvent("root:", name="parent")

    assert parent._bec_root_resolved_signals == {"file_event": ("file_event", parent.file_event)}
    assert "_bec_root_resolved_signals" not in type(parent).__dict__


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


def test_destroy_finishes_child_cleanup_when_root_hook_fails():
    from ophyd import Component, Device, Signal

    cleaned = []

    class Child(Device):
        value = Component(Signal, value=0)

        def destroy(self):
            cleaned.append(not self.value._destroyed)
            super().destroy()

    class Root(PSIDeviceBase):
        child = Component(Child)

        def on_destroy(self):
            raise RuntimeError("shutdown hook failed")

    root = Root(name="root")
    child = root.child
    with pytest.raises(RuntimeError, match="shutdown hook failed"):
        root.destroy()
    assert cleaned == [True]
    assert child.value._destroyed
    assert root.destroyed
    root.destroy()


def test_cancel_status_while_success_is_settling(device):
    from ophyd import Signal

    from ophyd_devices.utils.psi_device_base_utils import SubscriptionStatus

    signal = Signal(name="value", value=0)
    status = SubscriptionStatus(
        signal, lambda *, value, **_: value == 1, run=False, settle_time=0.1, timeout=1
    )
    device.cancel_on_stop(status)
    released = threading.Event()
    status.add_callback(lambda _: released.set())
    signal.put(1)
    device._stop_stoppable_status_objects()
    status.wait(timeout=1)
    assert released.wait(timeout=1)
    assert not device._stoppable_status_objects


@pytest.mark.parametrize("failed", [False, True])
def test_completed_statuses_are_removed_from_cancellation_registry(device, failed):
    """
    Successful and failed operations release their registry entries immediately.
    """
    status = StatusBase()
    device.cancel_on_stop(status)
    device.cancel_on_stop(status)
    assert device._stoppable_status_objects == [status]
    if failed:
        status.set_exception(RuntimeError("acquisition failed"))
    else:
        status.set_finished()
    assert device._stoppable_status_objects == []
    device.cancel_on_stop(status)
    assert device._stoppable_status_objects == []


def test_status_completing_during_registration_is_not_retained(device):
    """
    Completion between insertion and callback registration still removes the entry.
    """
    status = StatusBase()
    add_callback = status.add_callback

    def finish_before_callback(callback):
        status.set_finished()
        add_callback(callback)

    with mock.patch.object(status, "add_callback", side_effect=finish_before_callback):
        device.cancel_on_stop(status)
    assert not device._stoppable_status_objects


def test_concurrent_status_completion_and_stop_cancel_all_pending_work(device):
    """
    Concurrent removal cannot skip statuses in the detached cancellation batch.
    """
    from concurrent.futures import ThreadPoolExecutor

    from ophyd.utils.errors import InvalidState

    statuses = [StatusBase() for _ in range(50)]
    for status in statuses:
        device.cancel_on_stop(status)
    barrier = threading.Barrier(2)

    def complete():
        barrier.wait(timeout=2)
        for status in statuses:
            try:
                status.set_finished()
            except InvalidState:
                pass  # Stop won completion of this particular operation.

    with ThreadPoolExecutor(max_workers=1) as pool:
        completed = pool.submit(complete)
        barrier.wait(timeout=2)
        device._stop_stoppable_status_objects()
        completed.result(timeout=2)
    assert all(status.done for status in statuses)
    assert not device._stoppable_status_objects


def test_cooperative_groups_destroy_resources_before_disconnecting_signals():
    """
    Explicit child cleanup preserves owner order, signal access and lazy components.
    """
    from ophyd import Signal

    cleaned = []

    class Resource(Device):
        value = Cpt(Signal, value=1)

        def destroy(self):
            cleaned.append((self.name, not self.value._destroyed))
            super().destroy()

    class InnerGroup(Device):
        resource = Cpt(Resource)
        unused = Cpt(Resource, lazy=True)

        def destroy(self):
            cleaned.append((self.name, True))
            try:
                destroy_subdevices(self)
            finally:
                super().destroy()

    class OuterGroup(Device):
        inner = Cpt(InnerGroup)

        def destroy(self):
            cleaned.append((self.name, True))
            try:
                destroy_subdevices(self)
            finally:
                super().destroy()

    class Root(PSIDeviceBase):
        group = Cpt(OuterGroup)

    root = Root(name="root")
    resource = root.group.inner.resource
    root.destroy()
    assert cleaned == [
        ("root_group", True),
        ("root_group_inner", True),
        ("root_group_inner_resource", True),
    ]
    assert resource._destroyed
    assert "unused" not in root.group.inner._signals
    root.destroy()
    assert len(cleaned) == 3


def test_destroy_preserves_nested_psi_hook_access_to_live_child_signals():
    """
    Nested PSI devices retain ownership of hook-before-child shutdown ordering.
    """
    from ophyd import Signal

    cleaned = []

    class Resource(Device):
        value = Cpt(Signal, value=1)

        def destroy(self):
            cleaned.append("resource")
            super().destroy()

    class Child(PSIDeviceBase):
        resource = Cpt(Resource)

        def on_destroy(self):
            assert not self.resource.value._destroyed
            cleaned.append("child hook")

    class Group(Device):
        child = Cpt(Child)

        def destroy(self):
            cleaned.append("group")
            try:
                destroy_subdevices(self)
            finally:
                super().destroy()

    class Root(PSIDeviceBase):
        group = Cpt(Group)

    root = Root(name="root")
    root.destroy()
    assert cleaned == ["group", "child hook", "resource"]


def test_destroy_continues_groups_and_siblings_after_nested_cleanup_failure():
    """
    A failed resource cannot skip its grouping destructor or independent siblings.
    """
    cleaned = []

    class Resource(Device):
        def destroy(self):
            cleaned.append(self.name)
            super().destroy()
            if self.attr_name == "broken":
                raise RuntimeError("resource shutdown failed")

    class Group(Device):
        broken = Cpt(Resource)
        sibling = Cpt(Resource)

        def destroy(self):
            cleaned.append(self.name)
            super().destroy()
            raise RuntimeError("group shutdown failed")

    class Root(PSIDeviceBase):
        group = Cpt(Group)
        sibling = Cpt(Resource)

    root = Root(name="root")
    with pytest.raises(RuntimeError, match="group shutdown failed") as failure:
        root.destroy()
    assert cleaned == ["root_group", "root_group_broken", "root_group_sibling", "root_sibling"]
    assert "resource shutdown failed" in " ".join(failure.value.__notes__)
    assert root.destroyed


def test_destroy_checks_descendants_of_previously_destroyed_custom_group():
    """
    Ophyd can mark a group destroyed without running any descendant destroy methods.
    """
    cleaned = []

    class Resource(Device):
        def destroy(self):
            cleaned.append(self.name)
            super().destroy()

    class Group(Device):
        resource = Cpt(Resource)

        def destroy(self):
            super().destroy()

    class Root(PSIDeviceBase):
        group = Cpt(Group)

    root = Root(name="root")
    resource = root.group.resource
    root.group.destroy()
    assert not resource._destroyed
    root.destroy()
    assert cleaned == ["root_group_resource"]
    assert resource._destroyed


def test_custom_group_flushes_child_resource_before_child_destruction():
    """
    Owner cleanup can use a child handle, then explicitly release child resources.
    """
    import io

    from ophyd import Signal

    calls = []

    class Resource(Device):
        value = Cpt(Signal, value=1)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.handle = io.BytesIO()

        def destroy(self):
            assert not self.value._destroyed
            calls.append(("resource", self.handle.getvalue()))
            self.handle.close()
            super().destroy()

    class Group(Device):
        resource = Cpt(Resource)
        unused = Cpt(Resource, lazy=True)

        def destroy(self):
            self.resource.handle.write(b"final record")
            calls.append(("group", self.resource.handle.closed))
            try:
                destroy_subdevices(self)
            finally:
                super().destroy()

    class Root(PSIDeviceBase):
        group = Cpt(Group)

    root = Root(name="root")
    resource = root.group.resource
    root.destroy()
    assert calls == [("group", False), ("resource", b"final record")]
    assert resource.handle.closed
    assert resource.value._destroyed
    assert "unused" not in root.group._signals
    root.destroy()
    assert len(calls) == 2


def test_stop_cancels_statuses_and_attempts_native_shutdown_after_hook_failure():
    """
    A failing custom stop hook cannot skip interruption state, cancellation or child shutdown.
    """
    root = PSIDeviceBase(name="root")
    pending = StatusBase()
    root.cancel_on_stop(pending)
    observed = []

    def failing_hook():
        observed.append(root.stopped)
        raise RuntimeError("custom stop failed")

    try:
        with (
            mock.patch.object(root, "on_stop", side_effect=failing_hook),
            mock.patch.object(
                Device, "stop", autospec=True, side_effect=TimeoutError("native stop failed")
            ) as native,
        ):
            with pytest.raises(RuntimeError, match="custom stop failed") as error:
                root.stop()
            native.assert_called_once_with(root, success=False)
        assert observed == [False]  # Preserve the hook's original entry-state contract.
        assert root.stopped
        assert pending.done
        with pytest.raises(DeviceStoppedError):
            pending.wait(timeout=1)
        assert not root._stoppable_status_objects
        assert "native stop failed" in " ".join(error.value.__notes__)
    finally:
        root.destroy()


def test_native_stage_failure_can_unstage_for_rollback():
    from ophyd import Signal

    root = PSIDeviceBase(name="root")
    gain = Signal(name="gain", value=1)
    root.stage_sigs[gain] = 2
    original = gain.set

    def set_gain(value, **kwargs):
        if value == 2:
            raise RuntimeError("stage setting failed")
        return original(value, **kwargs)

    try:
        with (
            mock.patch.object(gain, "set", side_effect=set_gain),
            pytest.raises(RuntimeError, match="stage setting failed"),
        ):
            root.stage()
        assert root.staged == Staged.no
    finally:
        root.destroy()
        gain.destroy()


@pytest.fixture
def destruction_camera():
    """
    Provide observable camera input and a real preview timer without hardware I/O.
    """

    class Camera(CameraBase):
        def on_init(self) -> None:
            self.acquiring = False
            self.live_starts = 0

        def on_live_mode_starts(self) -> None:
            self.check_cancelled()
            self.acquiring = True
            self.live_starts += 1

        def on_live_mode_stops(self) -> None:
            self.acquiring = False

        def on_stop(self) -> None:
            self.stopped = True
            self.stop_live(update_preference=False).wait(timeout=self.io_timeout)

        def on_destroy(self) -> None:
            self.live_enabled.unsubscribe(self._live_subscription)
            self.on_stop()

    camera = Camera(name="camera", redis_update_frequency=20, io_timeout=1)
    yield camera
    camera._poll_stop.set()
    if camera._poll_thread is not None:
        camera._poll_thread.join(timeout=1)
    camera.destroy()


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_camera_cannot_restart_between_destroy_cleanup_steps(
    destruction_camera, cleanup_fails, monkeypatch
):
    """
    Destruction retains exclusive ownership after the camera hook has stopped live input.
    """
    camera = destruction_camera
    camera.start_live().wait(timeout=1)
    preview = camera._poll_thread
    entered, release = threading.Event(), threading.Event()

    def shutdown() -> None:
        entered.set()
        assert release.wait(timeout=2)
        if cleanup_fails:
            raise RuntimeError("task shutdown failed")

    monkeypatch.setattr(camera.task_handler, "shutdown", shutdown)
    with ThreadPoolExecutor(max_workers=1) as pool:
        destroying = pool.submit(camera.destroy)
        try:
            assert entered.wait(timeout=1)
            assert not camera.acquiring
            assert preview is not None and not preview.is_alive()
            for setup in (camera.start_live, camera.stage):
                with pytest.raises(DeviceStoppedError, match="destruction has begun"):
                    setup()
            camera.start_polling()
            assert camera._poll_thread is preview
            camera.destroy()  # An overlapping call must not run cleanup again.
        finally:
            release.set()
        if cleanup_fails:
            with pytest.raises(RuntimeError, match="task shutdown failed"):
                destroying.result(timeout=2)
        else:
            destroying.result(timeout=2)

    assert camera.destroyed
    assert camera.live_starts == 1
    assert not camera.acquiring
    for setup in (camera.start_live, camera.stage):
        with pytest.raises(DeviceStoppedError, match="destruction has begun"):
            setup()
    camera.start_polling()
    assert camera._poll_thread is preview
    assert not preview.is_alive()
    camera.destroy()


def test_live_start_acknowledged_after_destroy_cannot_restart_preview(
    destruction_camera, monkeypatch
):
    """
    A live request already awaiting acknowledgement cannot revive a destroyed camera.
    """
    camera = destruction_camera
    entered = threading.Event()
    acknowledged = StatusBase()
    original_start = camera.on_live_mode_starts

    def start() -> StatusBase:
        original_start()
        entered.set()
        return acknowledged

    monkeypatch.setattr(camera, "on_live_mode_starts", start)
    with ThreadPoolExecutor(max_workers=1) as pool:
        starting = pool.submit(camera.start_live)
        try:
            assert entered.wait(timeout=1)
            assert camera.acquiring
            camera.destroy()
        finally:
            acknowledged.set_finished()
        with pytest.raises(DeviceStoppedError):
            starting.result(timeout=2)
    assert camera.destroyed
    assert not camera.acquiring
    assert camera._poll_thread is None


def test_failed_native_destroy_can_retry_without_allowing_setup():
    """
    Failed native cleanup remains retryable while destruction permanently retires setup.
    """
    root = PSIDeviceBase(name="root")
    with mock.patch.object(Device, "destroy", side_effect=RuntimeError("native destroy failed")):
        with pytest.raises(RuntimeError, match="native destroy failed"):
            root.destroy()
    assert not root.destroyed
    assert root._destroying
    with pytest.raises(DeviceStoppedError, match="destruction has begun"):
        root.stage()
    root.destroy()
    assert root.destroyed
    root.destroy()
