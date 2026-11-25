"""Camera lifecycle contracts exercised without an acquisition backend or EPICS."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest import mock

import pytest
from ophyd import Component, Device, Kind, Signal

from ophyd_devices.interfaces.base_classes.camera_base import CameraBase
from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.utils.psi_device_base_utils import (
    CompareStatus,
    DeviceCleanupBlockedError,
    SequenceStatus,
    StatusBase,
)


class SoftCamera(CameraBase):
    """A backend whose ordinary hooks write one soft acquisition-state signal."""

    running = Component(Signal, value=0, kind=Kind.omitted)

    def on_init(self) -> None:
        self.events = []
        self.start_ack = None
        self.stop_ack = None
        self.startup_seen = Event()
        self.polled = Event()
        self.poll_count = 0

    def on_connected(self) -> None:
        self._live_ready = True

    def on_live_mode_starts(self) -> StatusBase | None:
        self.events.append("start")
        self.running.put(1)
        self.startup_seen.set()
        return self.start_ack

    def on_live_mode_stops(self) -> StatusBase | None:
        self.events.append("stop")
        if self.stop_ack is None:
            self.running.put(0)
            return None

        def stopped(status: StatusBase) -> None:
            if status.success:
                self.running.put(0)

        self.stop_ack.add_callback(stopped)
        return self.stop_ack

    def on_poll(self) -> None:
        if self._redis_preview_due():
            self.poll_count += 1
            self.polled.set()


@pytest.fixture
def camera():
    device = SoftCamera(
        name="camera", live_enabled=False, io_timeout=1, live_roi_update_frequency=0
    )
    device.on_connected()
    try:
        yield device
    finally:
        for status in (device.start_ack, device.stop_ack):
            if status is not None and not status.done:
                status.set_finished()
        device.start_ack = device.stop_ack = None
        device.destroy()


def test_settings_are_configuration_and_native_lifecycle_is_inherited(camera):
    configuration = camera.read_configuration()
    assert configuration["camera_live_enabled"]["value"] is False
    assert configuration["camera_use_scan_timing"]["value"] is True
    assert configuration["camera_live_follows_scan_timing"]["value"] is True
    assert configuration["camera_acquisition_source"]["value"] == "internal"
    assert configuration["camera_acquisition_mode"]["value"] == "continuous"
    assert "camera_running" not in configuration
    assert camera.events == []
    for method in ("stage", "trigger", "complete", "unstage"):
        assert getattr(CameraBase, method) is getattr(PSIDeviceBase, method)


def test_public_live_control_repeats_and_idle_stop_is_idempotent(camera):
    for _ in range(3):
        started = camera.start_live()
        assert started.done and started.success
        assert camera.running.get() == 1
        assert camera.live_enabled.get() is True
        stopped = camera.stop_live()
        assert stopped.done and stopped.success
        assert camera.running.get() == 0
        assert camera.live_enabled.get() is False
        camera.stop_live().wait(timeout=1)
    assert camera.events == ["start", "stop"] * 3


def test_internal_pause_and_resume_preserve_live_preference(camera):
    camera.start_live().wait(timeout=1)
    camera.stop_live(update_preference=False).wait(timeout=1)
    assert camera.live_enabled.get() is False
    assert camera._live_requested is True
    assert camera.running.get() == 0
    camera.start_live(update_preference=False).wait(timeout=1)
    assert camera.live_enabled.get() is True
    assert camera.running.get() == 1
    assert camera.events == ["start", "stop", "start"]


def test_disabled_live_resume_does_not_call_backend(camera):
    status = camera.start_live(update_preference=False)
    assert status.done and status.success
    assert camera.live_enabled.get() is False
    assert camera.running.get() == 0
    assert camera.events == []


@pytest.mark.parametrize("method", ["put", "set"])
def test_live_signal_updates_readback_only_after_start_acknowledgement(camera, method):
    camera.start_ack = StatusBase()
    result = getattr(camera.live_enabled, method)(True)
    status = result if method == "set" else camera.live_enabled._status
    try:
        assert camera.startup_seen.wait(timeout=1)
        assert not status.done
        assert camera.live_enabled.get() is False
    finally:
        camera.start_ack.set_finished()
    status.wait(timeout=1)
    assert camera.live_enabled.get() is True
    assert camera.running.get() == 1


@pytest.mark.parametrize("failed_status", [False, True])
def test_live_signal_start_failure_is_reported_by_wait(camera, monkeypatch, failed_status):
    def fail():
        if not failed_status:
            raise RuntimeError("IOC refused startup")
        status = StatusBase()
        status.set_exception(RuntimeError("IOC refused startup"))
        return status

    monkeypatch.setattr(camera, "on_live_mode_starts", fail)
    status = camera.live_enabled.set(True)
    with pytest.raises(RuntimeError, match="IOC refused startup"):
        status.wait(timeout=1)
    assert camera.live_enabled.get() is False
    assert camera._live_active is False


def test_live_signal_start_timeout_fails_status_and_stops_input(camera):
    camera.start_ack = StatusBase()
    status = camera.live_enabled.set(True, timeout=0.02)
    try:
        assert camera.startup_seen.wait(timeout=1)
        with pytest.raises(TimeoutError):
            status.wait(timeout=0.3)
        assert status.done
        assert not status.success
        assert camera.live_enabled.get() is False
        assert camera.running.get() == 0
    finally:
        camera.start_ack.set_finished()
        try:
            status.wait(timeout=1)
        except TimeoutError:
            pass


@pytest.mark.parametrize("fail", [False, True])
def test_live_signal_stop_retains_readback_until_acknowledgement(camera, monkeypatch, fail):
    camera.live_enabled.set(True).wait(timeout=1)
    camera.stop_ack = StatusBase()
    stopping = Event()
    original_stop = camera.on_live_mode_stops

    def stop():
        result = original_stop()
        stopping.set()
        return result

    monkeypatch.setattr(camera, "on_live_mode_stops", stop)
    status = camera.live_enabled.set(False)
    try:
        assert stopping.wait(timeout=1)
        assert not status.done
        assert camera.live_enabled.get() is True
    finally:
        if fail:
            camera.stop_ack.set_exception(RuntimeError("IOC refused shutdown"))
        else:
            camera.stop_ack.set_finished()
    if fail:
        with pytest.raises(RuntimeError, match="IOC refused shutdown"):
            status.wait(timeout=1)
        assert camera.live_enabled.get() is True
        assert camera.running.get() == 1
    else:
        status.wait(timeout=1)
        assert camera.live_enabled.get() is False
        assert camera.running.get() == 0


def test_live_start_waits_for_backend_acknowledgement(camera, monkeypatch):
    camera.start_ack = StatusBase()
    waiting_for_ack = Event()
    wait_timeouts = []
    original_wait = camera.start_ack.wait

    def wait_for_ack(*, timeout=None):
        wait_timeouts.append(timeout)
        waiting_for_ack.set()
        # The test drives this acknowledgement. Only the outer Future.result is
        # bounded, so a delayed observer cannot turn ordering into a timeout test.
        return original_wait(timeout=None)

    monkeypatch.setattr(camera.start_ack, "wait", wait_for_ack)
    with ThreadPoolExecutor(max_workers=1) as callers:
        startup = callers.submit(camera.start_live)
        try:
            assert waiting_for_ack.wait(timeout=1)
            assert wait_timeouts == [camera.io_timeout]
            assert not startup.done()
            assert camera._live_start_acknowledged is False
            assert camera._poll_thread is None
        finally:
            if not camera.start_ack.done:
                camera.start_ack.set_finished()
        status = startup.result(timeout=1)
    assert status is camera.start_ack
    assert status.success
    assert camera._live_start_acknowledged is True


def test_overlapping_live_stops_share_backend_acknowledgement(camera):
    camera.start_live().wait(timeout=1)
    camera.stop_ack = StatusBase()
    first = camera.stop_live()
    second = camera.stop_live()
    assert first is second
    assert not first.done
    assert camera.running.get() == 1
    assert camera.events == ["start", "stop"]
    camera.stop_ack.set_finished()
    first.wait(timeout=1)
    assert camera.running.get() == 0
    assert camera._live_active is False
    assert camera.live_enabled.get() is False


def test_timing_policy_signals_survive_live_transitions(camera):
    camera.use_scan_timing.put(False)
    camera.live_follows_scan_timing.put(False)
    camera.start_live().wait(timeout=1)
    camera.stop_live().wait(timeout=1)
    assert camera.use_scan_timing.get() is False
    assert camera.live_follows_scan_timing.get() is False
    camera.use_scan_timing.put(True)
    camera.live_follows_scan_timing.put(True)
    configuration = camera.read_configuration()
    assert configuration["camera_use_scan_timing"]["value"] is True
    assert configuration["camera_live_follows_scan_timing"]["value"] is True


def test_preview_timer_is_opt_in_and_can_stop_without_stopping_input(camera):
    camera.start_live().wait(timeout=1)
    assert camera.redis_update_frequency == 0
    assert camera._poll_thread is None
    assert camera.poll_count == 0
    assert camera._redis_preview_due() is False
    camera.redis_update_frequency = 100
    assert camera.polled.wait(timeout=1)
    timer = camera._poll_thread
    camera.redis_update_frequency = 0
    assert timer is not None and not timer.is_alive()
    camera.polled.clear()
    assert not camera.polled.wait(timeout=0.03)
    assert camera.running.get() == 1
    assert camera.live_enabled.get() is True
    assert camera.events == ["start"]


def test_device_stop_cancels_pending_work_and_stops_backend(camera):
    camera.redis_update_frequency = 100
    camera.start_live().wait(timeout=1)
    assert camera.polled.wait(timeout=1)
    timer = camera._poll_thread
    acquisition = StatusBase()
    camera.cancel_on_stop(acquisition)
    camera.stop()
    with pytest.raises(DeviceStoppedError):
        acquisition.wait(timeout=1)
    assert camera.stopped is True
    assert timer is not None and not timer.is_alive()
    assert camera.running.get() == 0
    assert camera.live_enabled.get() is False
    assert camera._live_requested is True
    assert camera.events == ["start", "stop"]


def test_destroy_finishes_preview_thread_and_prevents_restart(camera):
    camera.redis_update_frequency = 100
    camera.start_live().wait(timeout=1)
    assert camera.polled.wait(timeout=1)
    timer = camera._poll_thread
    camera.destroy()
    assert camera.destroyed
    assert timer is not None and not timer.is_alive()
    assert camera.events == ["start", "stop"]
    with pytest.raises(DeviceStoppedError, match="destruction"):
        camera.start_live()


def test_destroy_keeps_signals_connected_while_preview_is_busy(camera, monkeypatch):
    entered, release = Event(), Event()

    def poll():
        entered.set()
        release.wait(timeout=2)

    monkeypatch.setattr(camera, "on_poll", poll)
    camera.redis_update_frequency = 100
    camera.start_live().wait(timeout=1)
    try:
        assert entered.wait(timeout=1)
        camera.io_timeout = 0.05
        with pytest.raises(DeviceCleanupBlockedError, match="preview cleanup"):
            camera.destroy()
        assert not camera.destroyed
        assert not camera.running._destroyed
    finally:
        release.set()
    camera.io_timeout = 1
    camera.destroy()
    assert camera.destroyed


def test_destroy_keeps_signals_connected_until_live_stop_is_acknowledged(camera):
    camera.start_live().wait(timeout=1)
    camera.stop_ack = StatusBase()
    camera.io_timeout = 0.05
    with pytest.raises(DeviceCleanupBlockedError, match="live shutdown"):
        camera.destroy()
    assert not camera.destroyed
    assert not camera.running._destroyed
    camera.stop_ack.set_finished()
    camera.destroy()
    assert camera.destroyed


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("blocked", [False, True])
def test_camera_destroys_children_before_signals_and_respects_cleanup_refusal(nested, blocked):
    class Child(Device):
        value = Component(Signal, value=0)
        refuse_cleanup = blocked

        def destroy(self):
            assert not self.root.running._destroyed
            assert not self.value._destroyed
            if self.refuse_cleanup:
                raise DeviceCleanupBlockedError("ROI configuration is still running")
            self.root.events.append("child cleanup")
            super().destroy()

    class Group(Device):
        child = Component(Child)

    class CameraWithChild(SoftCamera):
        processing = Component(Group if nested else Child)

        def on_destroy(self):
            # Child teardown must survive replacing the hook without super().
            self.events.append("camera cleanup")

    device = CameraWithChild(name="camera", live_enabled=False)
    child = device.processing.child if nested else device.processing
    try:
        if blocked:
            with pytest.raises(DeviceCleanupBlockedError):
                device.destroy()
            assert not device.destroyed
            assert not child.value._destroyed
            assert not device.running._destroyed
            child.refuse_cleanup = False
        device.destroy()
        assert device.destroyed
        assert child._destroyed and child.value._destroyed
        assert device.events[-2:] == ["camera cleanup", "child cleanup"]
        device.destroy()  # No duplicate child teardown.
    finally:
        child.refuse_cleanup = False
        device.destroy()


def test_camera_destroy_keeps_signals_until_failure_cleanup_acknowledges(camera):
    acknowledgement = CompareStatus(camera.running, 1, run=False)
    sequence = SequenceStatus(
        steps=[lambda: StatusBase()], on_failure=lambda error: acknowledgement
    )
    camera.cancel_on_stop(sequence)
    with pytest.raises(DeviceCleanupBlockedError, match="signal cleanup"):
        camera.destroy()
    assert not camera.destroyed
    assert not camera.running._destroyed
    assert not sequence.done
    camera.running.put(1)
    with pytest.raises(DeviceStoppedError):
        sequence.wait(timeout=1)
    camera.destroy()
    assert camera.destroyed


def test_camera_destroy_accepts_committed_native_cancellation(camera, monkeypatch):
    pending = CompareStatus(camera.running, 1, run=False, timeout=60)
    release = Event()
    settled = pending._settled

    def delayed_notification():
        assert release.wait(timeout=2)
        settled()

    monkeypatch.setattr(pending, "_settled", delayed_notification)
    camera.cancel_on_stop(pending)
    try:
        camera.destroy()
        assert camera.destroyed
    finally:
        release.set()
        pending._callback_thread.join(timeout=1)
        assert not pending._callback_thread.is_alive()


@pytest.mark.parametrize("error", [TimeoutError("slow preview"), RuntimeError("bad preview")])
def test_live_poll_failures_retry_without_stopping_input(camera, error):
    attempts = 0

    def poll():
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise error
        camera.polled.set()

    camera.redis_update_frequency = 100
    with (
        mock.patch.object(camera, "on_poll", side_effect=poll),
        mock.patch.object(camera, "stop", wraps=camera.stop) as stop,
        mock.patch(
            "ophyd_devices.interfaces.base_classes.camera_base.bec_logger.logger.warning"
        ) as warning,
    ):
        camera.start_live().wait(timeout=1)
        assert camera.polled.wait(timeout=1)
        assert camera._poll_thread.is_alive()
        camera.stop_polling()
        assert attempts >= 3
        assert camera.running.get() == 1
        assert camera._live_active and not camera.stopped
        stop.assert_not_called()
        warning.assert_called_once()


def test_live_warning_cooldown_is_shared_across_sources(camera):
    camera._poll_stop.clear()
    with (
        mock.patch("ophyd_devices.interfaces.base_classes.camera_base.monotonic") as clock,
        mock.patch(
            "ophyd_devices.interfaces.base_classes.camera_base.bec_logger.logger.warning"
        ) as warning,
    ):
        for timestamp in (0, 1, 29.9, 30):
            clock.return_value = timestamp
            camera._log_live_preview_error(TimeoutError("offline"), source=f"roi{timestamp}")
        assert warning.call_count == 2
        camera._poll_stop.set()
        clock.return_value = 60
        camera._log_live_preview_error(TimeoutError("stopping"))
        assert warning.call_count == 2


def test_live_poll_cancellation_exits_without_stopping_input(camera):
    camera.redis_update_frequency = 100
    with (
        mock.patch.object(camera, "on_poll", side_effect=DeviceStoppedError("cancelled")),
        mock.patch.object(camera, "stop", wraps=camera.stop) as stop,
        mock.patch(
            "ophyd_devices.interfaces.base_classes.camera_base.bec_logger.logger.warning"
        ) as warning,
    ):
        camera.start_live().wait(timeout=1)
        camera._poll_thread.join(timeout=1)
        assert not camera._poll_thread.is_alive()
        assert camera.running.get() == 1
        stop.assert_not_called()
        warning.assert_not_called()
