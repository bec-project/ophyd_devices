"""Camera lifecycle contracts exercised without an acquisition backend or EPICS."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from ophyd import Component, Kind, Signal

from ophyd_devices.interfaces.base_classes.camera_base import CameraBase
from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.utils.psi_device_base_utils import StatusBase


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

    def on_stop(self) -> None:
        self.stop_live(update_preference=False).wait(timeout=self.io_timeout)

    def on_destroy(self) -> None:
        self.on_stop()
        self.live_enabled.unsubscribe(self._live_subscription)


@pytest.fixture
def camera():
    device = SoftCamera(name="camera", live_enabled=False, io_timeout=1)
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
    for method in ("stage", "trigger", "complete", "unstage", "stop", "destroy"):
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
    assert camera.live_enabled.get() is True
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
    camera.start_live().wait(timeout=1)
    acquisition = StatusBase()
    camera.cancel_on_stop(acquisition)
    camera.stop()
    with pytest.raises(DeviceStoppedError):
        acquisition.wait(timeout=1)
    assert camera.stopped is True
    assert camera.running.get() == 0
    assert camera.live_enabled.get() is True
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
