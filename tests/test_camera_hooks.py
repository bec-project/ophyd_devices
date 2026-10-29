"""Real PV subscriptions and publication, without a hidden acquisition backend."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import FunctionType
from types import SimpleNamespace as NS
from unittest import mock

import numpy as np
import pytest
from bec_server.device_server.tests.utils import DMMock
from ophyd import Component, Signal, Staged

from ophyd_devices.devices.areadetector import camera_components as ad_components
from ophyd_devices.devices.areadetector.alliedvision_camera import AlliedVisionCamera
from ophyd_devices.devices.areadetector.trigger_modes import VimbaTriggerMode
from ophyd_devices.interfaces.base_classes.camera_base import (
    AcquisitionMode,
    AcquisitionSource,
    CameraBase,
)
from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError
from ophyd_devices.sim.sim_ad_camera import SimADCamera
from ophyd_devices.tests.utils import patched_device
from ophyd_devices.utils.bec_roi_signals import ad_roi_signal as roi_implementation
from ophyd_devices.utils.bec_roi_signals.ad_roi_signal import ADROIProcessing
from ophyd_devices.utils.bec_signals import DynamicSignal, PreviewSignal


def wait(status):
    """Native staging may return a device list; acquisition returns a status."""
    if hasattr(status, "wait"):
        status.wait(timeout=2)


@contextmanager
def staging_during_priming(camera):
    """
    Invoke blocking stage on a test caller thread while driving IOC acknowledgements.
    """
    started = threading.Event()
    original = camera.cam.acquire.callback

    def acquire(value):
        if value == 1 and camera.cam.image_mode.get() == "Single":
            started.set()
        if original is not None:
            original(value)

    camera.cam.acquire.callback = acquire
    try:
        with ThreadPoolExecutor(max_workers=1) as callers:
            staged = callers.submit(camera.stage)
            assert started.wait(timeout=2), "Priming acquisition did not start"
            yield staged
    finally:
        camera.cam.acquire.callback = original


def set_scan(
    camera, priority="monitored", scan_type="software_triggered", *, software_trigger=None
):
    if software_trigger is None:
        software_trigger = priority == "monitored"
    camera.device_manager.add_device(camera.name, software_trigger=software_trigger)
    camera.device_manager.devices[camera.name].software_trigger = software_trigger
    camera.scan_info = NS(
        msg=NS(
            readout_priority={priority: [camera.name]},
            num_monitored_readouts=2,
            info={
                "exp_time": 0.1,
                "readout_time": 0.01,
                "frames_per_trigger": 3,
                "num_points": 2,
                "scan_type": scan_type,
            },
        )
    )


class PV(Signal):
    def __init__(self, name, value, writes, callback=None):
        self.writes = writes
        self._read_pv = NS(nelm=10000)
        self.callback = callback
        super().__init__(name=name, value=value)
        # Model the initial readback event delivered by an EPICS auto monitor.
        super().put(value)

    def put(self, value, **kwargs):
        self.writes.append((self.name, value))
        super().put(value)
        if self.callback is not None:
            self.callback(value)


class ROI:
    arm_capture = ADROIProcessing.arm_capture
    drain_capture = ADROIProcessing.drain_capture
    publish_capture = ADROIProcessing.publish_capture
    read_preview_values = ADROIProcessing.read_preview_values
    stop_capture = ADROIProcessing.stop_capture

    def on_connected(self):
        """The mock ROI needs no connection setup."""

    def __init__(self):
        self._capture_outputs = {}
        self._capture_offset = self._capture_start_count = 0
        self._capture_armed = False


class CameraUnderTest(CameraBase):
    measurement = Component(DynamicSignal, ndim=0, signals=["sum"], max_size=100)
    roi_preview = Component(PreviewSignal, ndim=1)

    def on_init(self):
        self._init_camera()
        self.writes = []
        self.hold_camera = False
        self._acquire_origin = 0
        self.delay_stats = False
        self.stats_timer = None
        pv = lambda name, value, callback=None: PV(name, value, self.writes, callback)
        self.cam = NS(
            **{
                name: pv(name, value)
                for name, value in {
                    "acquire": 0,
                    "acquire_time": 0.01,
                    "acquire_period": 0.02,
                    "num_images": 1,
                    "image_mode": "Multiple",
                    "array_callbacks": 1,
                    "array_counter": 0,
                    "trigger_mode": 0,
                }.items()
            }
        )
        stats = NS(
            **{
                name: pv(name, value)
                for name, value in {
                    "enable": "Enable",
                    "ts_acquire": 0,
                    "ts_acquire_status": 0,
                    "ts_current_index": 0,
                    "ts_array_counter": 0,
                    "time_stamp": 1000,
                    "unique_id": 0,
                    "ts_num_points": 100,
                    "ts_averaging_time": 0,
                    "ts_num_average": 1,
                    "ts_acquire_mode": 0,
                    "ts_read_mode": 0,
                    "ts_read": 0,
                    "ts_sum": np.array([]),
                    "ts_timestamp": np.array([]),
                    "sum": 3.0,
                }.items()
            }
        )
        self.roi = ROI()
        self.roi.dotted_name = "roi"
        self.roi.stats1 = stats
        self.roi.roi1 = NS(enable=pv("roi_enable", "Enable"))
        self.roi.manage_capture = False
        self.roi.active = pv("active", True)
        self.roi.selected_operations = pv("operations", ["sum"])
        self.roi.average_frames_per_trigger = pv("average", False)
        self.roi.result_scalar = self.measurement
        self.roi.preview = self.roi_preview
        self.roi.stage_sigs = {}
        self.roi.update_received = NS(
            block_updates=lambda **_: None, unblock_updates=lambda **_: None
        )
        self.image = NS(
            enable=pv("image_enable", "Enable"),
            unique_id=pv("id", 1),
            array_size=NS(width=pv("width", 2), height=pv("height", 2), depth=pv("depth", 1)),
            color_mode=pv("color", 0),
            array_data=pv("array", np.arange(4)),
        )

        def stats_command(value):
            if value == 1:
                # The IOC resets internal storage, retaining old waveform records.
                stats.ts_current_index.put(0)
            stats.ts_acquire_status.put(value)

        stats.ts_acquire.callback = stats_command

        def read_stats(value):
            if stats.ts_acquire_status.get() == 1 and stats.ts_current_index.get() == 0:
                stats.ts_sum.put(np.array([]))
                stats.ts_timestamp.put(np.array([]))

        stats.ts_read.callback = read_stats

        def acquire(value):
            if value == 1:
                self._acquire_origin = int(self.cam.array_counter.get())
            if (
                value == 1
                and self.cam.image_mode.get() == "Multiple"
                and self.cam.trigger_mode.get() == 0
                and not self.hold_camera
            ):
                self.emit_frames(int(self.cam.num_images.get()))

        self.cam.acquire.callback = acquire

    def emit_frames(self, frames):
        stats = self.roi.stats1
        identifier = int(self.cam.array_counter.get()) + frames - 1
        stats.sum.put(float(identifier))
        stats.unique_id.put(identifier)
        stats.time_stamp.put(1000 + identifier)
        if stats.ts_acquire_status.get() == 1:
            start = len(stats.ts_sum.get())

            def stats_arrive():
                stats.ts_sum.put(np.r_[stats.ts_sum.get(), np.arange(frames, dtype=float)])
                stats.ts_timestamp.put(
                    np.r_[
                        stats.ts_timestamp.get(),
                        np.arange(start, start + frames, dtype=float) + 1000,
                    ]
                )
                capacity = int(stats.ts_num_points.get())
                stats.ts_sum.put(stats.ts_sum.get()[:capacity])
                stats.ts_timestamp.put(stats.ts_timestamp.get()[:capacity])
                index = min(start + frames, capacity)
                stats.time_stamp.put(1000 + int(stats.ts_array_counter.get()) + frames)
                stats.unique_id.put(int(self.cam.array_counter.get()) + frames - 1)
                stats.ts_current_index.put(index)
                stats.ts_array_counter.put(int(stats.ts_array_counter.get()) + frames)

            if self.delay_stats:
                self.stats_timer = threading.Timer(0.04, stats_arrive)
                self.stats_timer.start()
            else:
                stats_arrive()
        self.cam.array_counter.put(self.cam.array_counter.get() + frames)
        if self.cam.image_mode.get() == "Multiple" and (
            self.cam.array_counter.get() - self._acquire_origin >= self.cam.num_images.get()
        ):
            self.cam.acquire.put(0)

    def walk_subdevices(self, *, include_lazy=False):
        yield "roi", self.roi


def camera_test_class(name, implementation):
    """Run concrete methods without instantiating the EPICS signal descriptors."""
    methods = {
        key: value
        for key, value in vars(implementation).items()
        if isinstance(value, FunctionType) and key != "on_init"
    }
    methods.update(
        _init_camera=implementation.on_init,
        internal_trigger_mode=implementation.internal_trigger_mode,
        external_trigger_mode=implementation.external_trigger_mode,
    )
    return type(name, (CameraUnderTest,), methods)


AlliedVisionUnderTest = camera_test_class("AlliedVisionUnderTest", AlliedVisionCamera)
SimCameraUnderTest = camera_test_class("SimCameraUnderTest", SimADCamera)


@pytest.fixture(params=[AlliedVisionUnderTest, SimCameraUnderTest], ids=["alliedvision", "sim_ad"])
def camera(monkeypatch, request):
    monkeypatch.setattr(ad_components, "ADROIProcessing", ROI)
    monkeypatch.setattr(
        roi_implementation,
        "NDPLUGIN_STATS_CONFIG",
        {"sum": {"scalar_outputs": ["sum"], "source_signals": {"sum": "ts_sum"}}},
    )
    device = request.param(
        name="camera", device_manager=DMMock(), io_timeout=2, acquisition_timeout=0.3
    )
    device.on_connected()
    device.writes.clear()
    set_scan(device)
    try:
        yield device
    finally:
        if device.stats_timer is not None:
            device.stats_timer.join(timeout=1)
        device.destroy()


def test_immediate_camera_completion_is_observed_and_results_are_published(camera):
    wait(camera.stage())
    camera.writes.clear()
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
        camera.trigger().wait(timeout=2)
    assert result.call_count == 3
    names = [name for name, value in camera.writes]
    assert names.index("ts_acquire") < names.index("acquire")
    assert camera.roi.stats1.ts_acquire_status.get() == 0
    assert camera.cam.array_counter.get() == 3
    assert not camera.cam.acquire._callbacks[camera.cam.acquire.SUB_VALUE]
    assert not camera.roi.stats1.ts_current_index._callbacks[
        camera.roi.stats1.ts_current_index.SUB_VALUE
    ]
    camera.complete().wait(timeout=2)
    wait(camera.unstage())
    assert camera.cam.acquire.get() == 1
    assert camera.cam.acquire_time.get() == pytest.approx(0.09)


def test_status_includes_delayed_stats_drain_and_publication(camera):
    wait(camera.stage())
    camera.delay_stats = True
    trigger = camera.trigger()
    time.sleep(0.01)
    assert not trigger.done
    trigger.wait(timeout=2)
    assert camera.measurement.get().metadata["frame_ids"] == [2]


@pytest.mark.parametrize("scan_type", ["hardware_triggered", "fly"])
def test_baseline_uses_internal_trigger_mode_during_external_scan(camera, scan_type):
    set_scan(camera, "baseline", scan_type)
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
        wait(camera.stage())
        assert camera.staged == Staged.yes
        assert camera.cam.array_counter.get() == 0
        assert result.call_count == 0
        wait(camera.pre_scan())
        assert camera.cam.trigger_mode.get() == camera.internal_trigger_mode
        assert camera.cam.array_counter.get() == camera.frames_per_trigger
        assert camera.cam.acquire.get() == 0
        assert result.call_count == 1
        assert camera.measurement.get().metadata["correlation_group"] == "baseline"
        camera.complete().wait(timeout=2)
        assert result.call_count == 1
    wait(camera.unstage())


def test_baseline_reduces_frames_to_one_value_and_final_drain_does_not_repeat(camera):
    set_scan(camera, "baseline")
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
        wait(camera.stage())
        assert result.call_count == 0
        wait(camera.pre_scan())
        camera.complete().wait(timeout=2)
    assert result.call_count == 1
    message = camera.measurement.get()
    assert message.signals[camera.measurement.name]["value"] == 1
    assert message.metadata["frame_ids"] == [0, 1, 2]
    assert message.metadata["correlation_group"] == "baseline"


def test_abort_cancels_subscriptions_and_stops_camera_and_stats(camera):
    wait(camera.stage())
    camera.hold_camera = True
    trigger = camera.trigger()
    deadline = time.monotonic() + 1
    while not camera.cam.acquire.get() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert camera.cam.acquire.get() == 1
    camera.stop()
    with pytest.raises(DeviceStoppedError, match="stopped"):
        trigger.wait(timeout=1)
    assert camera.cam.acquire.get() == 0
    assert camera.roi.stats1.ts_acquire_status.get() == 0
    assert not camera.cam.acquire._callbacks[camera.cam.acquire.SUB_VALUE]


def test_timeout_fails_operation_and_cleanup_stops_hardware(camera):
    wait(camera.stage())
    camera.io_timeout = 0.3
    camera.hold_camera = True
    with pytest.raises(TimeoutError):
        camera.trigger().wait(timeout=2)
    assert camera.cam.acquire.get() == 0
    assert camera.roi.stats1.ts_acquire_status.get() == 0


def test_stream_stats_are_armed_before_external_input_and_drain_once(camera):
    if isinstance(camera, SimCameraUnderTest):
        pytest.skip("simDetector draft has no external pulse source")
    camera.external_trigger_mode = VimbaTriggerMode.ON
    camera.acquisition_source.put("external")
    set_scan(camera, "async", "hardware_triggered")
    wait(camera.stage())
    commands = [(n, v) for n, v in camera.writes if n in ("ts_acquire", "acquire")]
    assert commands.index(("ts_acquire", 1)) < commands.index(("acquire", 1))
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
        camera.emit_frames(6)
        camera.complete().wait(timeout=2)
    assert result.call_count == 6
    assert camera.measurement.get().metadata["correlation_group"] == "async"


def test_async_polling_and_completion_share_a_cursor(camera):
    set_scan(camera, "async")
    wait(camera.stage())
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
        camera.emit_frames(2)
        camera.on_poll()
        camera.complete().wait(timeout=2)
    assert result.call_count == 2
    assert camera.cam.acquire.get() == 0


def test_live_preview_uses_preview_signals(camera):
    camera.redis_update_frequency = 2
    camera.on_poll()
    image = camera.preview.get()
    assert camera.roi_preview.get().metadata["outputs"] == ["sum"]
    np.testing.assert_array_equal(image.data, np.arange(4).reshape(2, 2))


def test_publication_failure_does_not_report_success(camera):
    wait(camera.stage())
    with (
        mock.patch.object(camera.measurement, "put", side_effect=RuntimeError("publish failed")),
        pytest.raises(RuntimeError, match="publish failed"),
    ):
        camera.trigger().wait(timeout=2)
    assert camera.cam.acquire.get() == 0
    assert camera.roi.stats1.ts_acquire_status.get() == 0


def test_capacity_rejection_stops_before_camera_input(camera):
    set_scan(camera, "async")
    with (
        mock.patch.object(camera.roi.stats1.ts_num_points, "get", return_value=2),
        pytest.raises(ValueError, match="exceeds IOC buffer capacity"),
    ):
        wait(camera.stage())
    assert ("acquire", 1) not in camera.writes
    assert camera.cam.acquire.get() == 0
    assert camera.roi.stats1.ts_acquire_status.get() == 0


def test_separate_bursts_keep_scan_frame_ids_and_do_not_republish(camera):
    camera.cam.array_counter.put(7)
    wait(camera.stage())
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as results:
        camera.trigger().wait(timeout=2)
        camera.trigger().wait(timeout=2)
        camera.complete().wait(timeout=2)
    assert results.call_count == 6
    assert [call.kwargs["metadata"]["frame_ids"] for call in results.call_args_list] == [
        [0],
        [1],
        [2],
        [3],
        [4],
        [5],
    ]


def test_manual_controller_settings_survive_successive_scans(camera):
    camera.cam.num_images.put(4)
    camera.cam.acquire_time.put(0.04)
    camera.cam.acquire_period.put(0.05)
    camera.live_follows_scan_timing.put(False)
    camera.use_scan_timing.put(False)
    for _ in range(2):
        wait(camera.stage())
        assert camera.frames_per_trigger == 4
        camera.trigger().wait(timeout=2)
        camera.complete().wait(timeout=2)
        wait(camera.unstage())
        assert camera.cam.num_images.get() == 4
        assert camera.cam.acquire_time.get() == 0.04
        assert camera.cam.acquire_period.get() == 0.05
        assert camera.cam.acquire.get() == 1


def test_rejected_scan_stops_input_and_resets_scan_state(camera):
    camera.scan_info.msg.info["exp_time"] = 0
    with pytest.raises(ValueError):
        wait(camera.stage())
    assert camera.cam.acquire.get() == 0
    assert camera.stopped
    assert camera.staged == Staged.yes
    assert not hasattr(camera, "_saved_settings")


def test_failed_acquisition_resets_scan_state_and_can_restore_live(camera):
    wait(camera.stage())
    with (
        mock.patch.object(camera.roi, "publish_capture", side_effect=RuntimeError("read failed")),
        pytest.raises(RuntimeError, match="read failed"),
    ):
        camera.trigger().wait(timeout=2)
    assert camera.cam.acquire.get() == 0
    assert camera.stopped
    assert camera.staged == Staged.yes
    wait(camera.unstage())
    assert camera.cam.acquire_time.get() == pytest.approx(0.09)
    assert camera.cam.acquire.get() == 1


def test_live_hooks_bracket_scan_without_calling_abort_hook(camera):
    with (
        mock.patch.object(
            camera, "on_live_mode_starts", wraps=camera.on_live_mode_starts
        ) as starts,
        mock.patch.object(camera, "on_live_mode_stops", wraps=camera.on_live_mode_stops) as stops,
        mock.patch.object(camera, "on_stop") as abort,
        mock.patch.object(camera, "on_complete", wraps=camera.on_complete) as complete,
    ):
        wait(camera.stage())
        assert stops.call_count == 1
        assert starts.call_count == 0
        camera.trigger().wait(timeout=2)
        camera.complete().wait(timeout=2)
        camera.complete().wait(timeout=2)
        wait(camera.unstage())
        assert complete.call_count == 2
        assert starts.call_count == 1
        assert stops.call_count == 1
        abort.assert_not_called()


def test_live_toggle_calls_only_the_matching_hook(camera):
    with (
        mock.patch.object(
            camera, "on_live_mode_starts", wraps=camera.on_live_mode_starts
        ) as starts,
        mock.patch.object(camera, "on_live_mode_stops", wraps=camera.on_live_mode_stops) as stops,
        mock.patch.object(camera, "on_stop") as abort,
    ):
        camera.live_enabled.put(False)
        assert stops.call_count == 1
        starts.assert_not_called()
        assert camera.cam.acquire.get() == 0
        camera.live_enabled.put(True)
        assert starts.call_count == 1
        assert stops.call_count == 1
        assert camera.cam.acquire.get() == 1
        abort.assert_not_called()


def test_public_live_methods_return_status_and_update_preference(camera):
    camera.stop_live().wait(timeout=2)
    assert not camera.live_enabled.get()
    assert camera.cam.acquire.get() == 0
    camera.start_live().wait(timeout=2)
    assert camera.live_enabled.get()
    assert camera.cam.acquire.get() == 1
    wait(camera.stage())
    with pytest.raises(RuntimeError, match="during a scan"):
        camera.start_live()
    with pytest.raises(RuntimeError, match="during a scan"):
        camera.stop_live()
    wait(camera.unstage())


def test_sim_rejects_external_triggering_and_leaves_input_stopped(camera):
    if not isinstance(camera, SimCameraUnderTest):
        pytest.skip("simDetector-specific capability check")
    set_scan(camera, "async", "hardware_triggered")
    camera.acquisition_source.put("external")
    with pytest.raises(NotImplementedError, match="External triggering"):
        wait(camera.stage())
    assert camera.cam.acquire.get() == 0
    assert camera.stopped


def test_inactive_roi_can_be_reenabled_for_the_next_burst(camera):
    wait(camera.stage())
    camera.roi.active.put(False)
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as results:
        camera.trigger().wait(timeout=2)
        results.assert_not_called()
        assert camera.roi.roi1.enable.get() == "Disable"
        assert camera.roi.stats1.enable.get() == "Disable"
        camera.roi.active.put(True)
        camera.trigger().wait(timeout=2)
        assert results.call_count == 3
        assert camera.roi.roi1.enable.get() == "Enable"
        assert camera.roi.stats1.enable.get() == "Enable"


def test_roi_rejects_competing_legacy_capture_owner(camera):
    wait(camera.stage())
    camera.roi.manage_capture = True
    with pytest.raises(RuntimeError, match="manage_capture=False"):
        camera.trigger().wait(timeout=2)
    assert camera.cam.acquire.get() == 0


def test_redis_preview_is_disabled_by_default_without_pv_reads(camera):
    assert camera.redis_update_frequency == 0
    with (
        mock.patch.object(camera.image.array_data, "get") as read,
        mock.patch.object(camera.preview, "put") as put,
    ):
        camera.on_poll()
        read.assert_not_called()
        put.assert_not_called()


def test_redis_preview_frequency_throttles_reads_and_puts(camera):
    camera.redis_update_frequency = 2
    with (
        mock.patch(f"{CameraBase.__module__}.monotonic", side_effect=[0.0, 0.1, 0.5]),
        mock.patch.object(
            camera.image.array_data, "get", wraps=camera.image.array_data.get
        ) as read,
        mock.patch.object(camera.preview, "put", wraps=camera.preview.put) as put,
    ):
        for identifier in (2, 3, 4):
            camera.image.unique_id.put(identifier)
            camera.components.publish_previews()
        assert read.call_count == 2
        assert put.call_count == 2


@pytest.mark.parametrize("frequency", [0, 2])
def test_preview_transports_describe_ioc_stream_without_publishing(camera, frequency):
    transport = {
        "transport": "zmq",
        "address": "tcp://ioc.example:5555",
        "topic": "image",
        "encoder": "adzmq-array-1.0",
    }
    device = type(camera)(
        name="described",
        device_manager=DMMock(),
        preview_transports={"preview": [transport]},
        redis_update_frequency=frequency,
    )
    try:
        described = device.preview.signal_info.transports
        assert len(described) == (2 if frequency else 1)
        if frequency:
            assert described[1].transport == "redis"
        assert described[0].address == transport["address"]
        assert device._poll_thread is None
        assert device.preview.get() is None
    finally:
        device.destroy()


@pytest.mark.parametrize("frequency", [-1, float("nan"), float("inf")])
def test_invalid_redis_frequency_is_rejected_before_initialization(camera, frequency):
    with pytest.raises(ValueError, match="redis_update_frequency"):
        type(camera)(name="invalid", redis_update_frequency=frequency, device_manager=DMMock())


def test_stage_component_rejects_unconfigured_external_trigger_mode_before_pv_writes(camera):
    set_scan(camera, "async")
    camera.acquisition_source.put("external")
    camera._staged = Staged.yes
    before = list(camera.writes)
    with pytest.raises(NotImplementedError, match="External triggering"):
        camera.components.stage_camera()
    assert camera.writes == before
    assert camera.cam.acquire.get() == 1


def test_external_completion_uses_actual_received_frames(camera):
    if isinstance(camera, SimCameraUnderTest):
        pytest.skip("simDetector draft has no external pulse source")
    camera.external_trigger_mode = VimbaTriggerMode.ON
    camera.acquisition_source.put("external")
    set_scan(camera, "async", "hardware_triggered")
    wait(camera.stage())
    camera.emit_frames(3)
    camera.complete().wait(timeout=2)
    assert camera.cam.array_counter.get() == 3
    assert camera.cam.acquire.get() == 0


def test_roi_discovery_is_fresh_and_excludes_other_subdevices(camera):
    other = ROI()
    other.dotted_name = "nested.other_roi"
    assert camera.components.get_rois() == [camera.roi]
    with mock.patch.object(
        camera,
        "walk_subdevices",
        return_value=iter(
            [("roi", camera.roi), ("unrelated", object()), ("nested.other_roi", other)]
        ),
    ) as walk:
        assert camera.components.get_rois() == [camera.roi, other]
        walk.assert_called_once_with(include_lazy=True)
    assert camera.components.get_rois() == [camera.roi]
    assert not hasattr(camera, "sources")


def test_sim_ioc_layout_has_two_independent_roi_stats_pairs():
    with patched_device(SimADCamera, name="sim", prefix="DET:", device_manager=DMMock()) as device:
        try:
            first, second = device.components.get_rois()
            assert first is device.roi1
            assert second is device.roi2
            assert first.roi1.prefix == "DET:ROI1:"
            assert first.stats1.prefix == "DET:Stats1:"
            assert second.roi1.prefix == "DET:ROI2:"
            assert second.stats1.prefix == "DET:Stats2:"
            assert first.result_scalar is not second.result_scalar
        finally:
            device.destroy()


def test_two_rois_publish_independently_and_can_be_disabled_separately(camera):
    second = ROI()
    second.dotted_name = "roi2"
    second.manage_capture = False
    second.stats1 = NS(
        **{
            name: PV(f"roi2_{name}", signal.get(), camera.writes)
            for name, signal in vars(camera.roi.stats1).items()
        }
    )
    second.roi1 = NS(enable=PV("roi2_enable", "Enable", camera.writes))
    second.active = PV("roi2_active", True, camera.writes)
    second.selected_operations = PV("roi2_operations", ["sum"], camera.writes)
    second.average_frames_per_trigger = PV("roi2_average", False, camera.writes)
    second.result_scalar = DynamicSignal(
        name="second_result", ndim=0, max_size=100, signals=["sum"], parent=camera
    )
    second.preview = PreviewSignal(name="second_preview", ndim=1, parent=camera)
    second.update_received = NS(block_updates=lambda **_: None, unblock_updates=lambda **_: None)
    camera.roi2 = second

    def reset(value):
        if value == 1:
            second.stats1.ts_current_index.put(0)
        second.stats1.ts_acquire_status.put(value)

    second.stats1.ts_acquire.callback = reset

    def read_second(value):
        if second.stats1.ts_acquire_status.get() == 1 and second.stats1.ts_current_index.get() == 0:
            second.stats1.ts_sum.put(np.array([]))
            second.stats1.ts_timestamp.put(np.array([]))

    second.stats1.ts_read.callback = read_second
    original_emit = camera.emit_frames

    def emit(frames):
        if second.stats1.ts_acquire_status.get() == 1:
            start = len(second.stats1.ts_sum.get())
            second.stats1.ts_sum.put(np.r_[second.stats1.ts_sum.get(), np.arange(frames) + 100])
            second.stats1.ts_timestamp.put(
                np.r_[second.stats1.ts_timestamp.get(), np.arange(start, start + frames) + 1000]
            )
            second.stats1.ts_current_index.put(start + frames)
        original_emit(frames)

    with (
        mock.patch.object(
            camera, "walk_subdevices", return_value=[("roi", camera.roi), ("roi2", second)]
        ),
        mock.patch.object(camera, "emit_frames", side_effect=emit),
        mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as first_put,
        mock.patch.object(
            second.result_scalar, "put", wraps=second.result_scalar.put
        ) as second_put,
    ):
        wait(camera.stage())
        camera.trigger().wait(timeout=2)
        assert first_put.call_count == second_put.call_count == 3
        assert first_put.call_args.kwargs["metadata"]["source"] == "roi.result_scalar"
        assert second_put.call_args.kwargs["metadata"]["source"] == "roi2.result_scalar"
        assert second.result_scalar.get().signals["second_result"]["value"] == 102
        second.active.put(False)
        camera.trigger().wait(timeout=2)
        assert first_put.call_count == 6
        assert second_put.call_count == 3
        second.active.put(True)
        camera.trigger().wait(timeout=2)
        assert first_put.call_count == 9
        assert second_put.call_count == 6
        camera.complete().wait(timeout=2)
        wait(camera.unstage())


def test_live_follows_latest_scan_timing_by_default(camera):
    assert camera.live_follows_scan_timing.get() is True
    wait(camera.stage())
    camera.trigger().wait(timeout=2)
    camera.complete().wait(timeout=2)
    wait(camera.unstage())
    assert camera.cam.acquire_time.get() == pytest.approx(0.09)
    assert camera.cam.acquire_period.get() == pytest.approx(0.1)
    camera.scan_info.msg.info["exp_time"] = 0.2
    wait(camera.stage())
    camera.trigger().wait(timeout=2)
    camera.complete().wait(timeout=2)
    wait(camera.unstage())
    assert camera.cam.acquire_time.get() == pytest.approx(0.19)
    assert camera.cam.acquire_period.get() == pytest.approx(0.2)


def test_live_timing_switch_during_scan_is_applied_only_on_resume(camera):
    camera.cam.acquire_time.put(0.03)
    camera.cam.acquire_period.put(0.04)
    wait(camera.stage())
    with mock.patch.object(
        camera.cam.acquire_time, "put", wraps=camera.cam.acquire_time.put
    ) as put:
        camera.live_follows_scan_timing.put(False)
        put.assert_not_called()
    assert camera.cam.acquire_time.get() == pytest.approx(0.09)
    camera.trigger().wait(timeout=2)
    camera.complete().wait(timeout=2)
    wait(camera.unstage())
    assert camera.cam.acquire_time.get() == 0.03
    assert camera.cam.acquire_period.get() == 0.04
    camera.live_follows_scan_timing.put(True)
    camera.start_live().wait(timeout=2)
    assert camera.cam.acquire_time.get() == pytest.approx(0.09)


def test_manual_scan_settings_are_read_from_controller(camera):
    camera.use_scan_timing.put(False)
    camera.cam.acquire_time.put(0.05)
    camera.cam.acquire_period.put(0.06)
    camera.cam.num_images.put(4)
    wait(camera.stage())
    assert camera.exposure == 0.05
    assert camera.period == 0.06
    assert camera.frames_per_trigger == 4


def test_invalid_manual_scan_timing_leaves_input_stopped(camera):
    camera.use_scan_timing.put(False)
    camera.cam.acquire_time.put(0.2)
    camera.cam.acquire_period.put(0.1)
    with pytest.raises(ValueError, match="period >= exposure"):
        wait(camera.stage())
    assert camera.cam.acquire.get() == 0
    assert camera.cam.acquire_time.get() == 0.2


def test_live_sync_disabled_preserves_controller_edits_outside_scans(camera):
    camera.live_follows_scan_timing.put(False)
    camera.cam.acquire_time.put(0.03)
    camera.cam.acquire_period.put(0.04)
    camera.start_live().wait(timeout=2)
    assert camera.cam.acquire_time.get() == 0.03
    assert camera.cam.acquire_period.get() == 0.04
    for name in (
        "live_exposure",
        "live_period",
        "scan_exposure",
        "scan_period",
        "scan_frames_per_trigger",
    ):
        assert not hasattr(camera, name)


def test_disabled_sync_restores_pre_scan_controller_timing(camera):
    camera.live_follows_scan_timing.put(False)
    camera.cam.acquire_time.put(0.03)
    camera.cam.acquire_period.put(0.04)
    for _ in range(2):
        wait(camera.stage())
        assert camera.cam.acquire_time.get() == pytest.approx(0.09)
        camera.trigger().wait(timeout=2)
        camera.complete().wait(timeout=2)
        wait(camera.unstage())
        assert camera.cam.acquire_time.get() == 0.03
        assert camera.cam.acquire_period.get() == 0.04
        assert camera.components._pre_scan_timing is None


def test_timing_snapshot_survives_failed_scan_until_live_resume(camera):
    camera.live_follows_scan_timing.put(False)
    camera.cam.acquire_time.put(0.03)
    camera.cam.acquire_period.put(0.04)
    wait(camera.stage())
    with (
        mock.patch.object(camera.roi, "publish_capture", side_effect=RuntimeError("read failed")),
        pytest.raises(RuntimeError, match="read failed"),
    ):
        camera.trigger().wait(timeout=2)
    assert camera.cam.acquire.get() == 0
    assert camera.components._pre_scan_timing == (0.03, 0.04)
    wait(camera.unstage())
    assert camera.cam.acquire_time.get() == 0.03
    assert camera.cam.acquire_period.get() == 0.04
    assert camera.components._pre_scan_timing is None


def test_timing_restore_waits_until_live_is_reenabled(camera):
    camera.live_follows_scan_timing.put(False)
    camera.cam.acquire_time.put(0.03)
    camera.cam.acquire_period.put(0.04)
    wait(camera.stage())
    camera.live_enabled.put(False)
    camera.trigger().wait(timeout=2)
    camera.complete().wait(timeout=2)
    wait(camera.unstage())
    assert camera.cam.acquire.get() == 0
    assert camera.components._pre_scan_timing == (0.03, 0.04)
    camera.start_live().wait(timeout=2)
    assert camera.cam.acquire_time.get() == 0.03
    assert camera.cam.acquire_period.get() == 0.04


def test_camera_implements_backend_logic_only_through_normal_hooks(camera):
    for name in (
        "_initialize_settings",
        "_resolve_scan_settings",
        "_validate_scan",
        "_stop_acquisition",
        "_close_backend",
        "_connect_backend",
    ):
        assert not hasattr(camera, name)
    with mock.patch.object(
        camera.components, "resolve_scan_settings", wraps=camera.components.resolve_scan_settings
    ) as resolve:
        wait(camera.stage())
        resolve.assert_called_once()


def test_camera_uses_the_standard_device_lifecycle(camera):
    from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase

    for method in (
        "stage",
        "pre_scan",
        "trigger",
        "kickoff",
        "complete",
        "unstage",
        "stop",
        "destroy",
    ):
        assert getattr(CameraBase, method) is getattr(PSIDeviceBase, method)
    assert not hasattr(camera, "_worker")
    assert not hasattr(camera, "_hook_context")
    assert camera._poll_thread is None
    with mock.patch.object(
        camera.task_handler, "submit_task", side_effect=AssertionError("No acquisition tasks")
    ):
        wait(camera.stage())
        camera.trigger().wait(timeout=2)
        camera.complete().wait(timeout=2)
        wait(camera.unstage())


def test_async_rois_publish_on_stats_events_before_completion(camera):
    set_scan(camera, "async")
    wait(camera.stage())
    published = threading.Event()
    token = camera.measurement.subscribe(lambda **_: published.set(), run=False)
    try:
        with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
            camera.emit_frames(2)
            assert published.wait(timeout=1)
            camera.complete().wait(timeout=2)
            assert result.call_count == 2
        assert camera._poll_thread is None
        assert not camera.components._stream_statuses
    finally:
        camera.measurement.unsubscribe(token)


def test_redis_preview_timer_uses_a_normal_thread_and_stops_for_scans(camera):
    camera.redis_update_frequency = 20
    published = threading.Event()
    token = camera.preview.subscribe(lambda **_: published.set(), run=False)
    try:
        with mock.patch.object(
            camera.task_handler, "submit_task", side_effect=AssertionError("No preview tasks")
        ):
            camera.start_live().wait(timeout=2)
            assert published.wait(timeout=1)
            assert camera._poll_thread.is_alive()
            wait(camera.stage())
            assert not camera._poll_thread.is_alive()
            camera.trigger().wait(timeout=2)
            camera.complete().wait(timeout=2)
            wait(camera.unstage())
            assert camera._poll_thread.is_alive()
            camera.stop()
            assert not camera._poll_thread.is_alive()
    finally:
        camera.preview.unsubscribe(token)


def test_trigger_returns_before_stats_arming_is_acknowledged(camera):
    wait(camera.stage())
    stats = camera.roi.stats1
    requested = threading.Event()
    original = stats.ts_acquire.callback

    def hold_ack(value):
        if value == 1:
            requested.set()
        else:
            original(value)

    stats.ts_acquire.callback = hold_ack
    trigger = camera.trigger()
    assert requested.wait(timeout=1)
    assert not trigger.done
    assert camera.cam.acquire.get() == 0
    stats.ts_current_index.put(0)
    stats.ts_acquire_status.put(1)
    trigger.wait(timeout=2)
    assert camera.measurement.get().metadata["frame_ids"] == [2]


def test_async_stage_returns_before_stats_arming_is_acknowledged(camera):
    set_scan(camera, "async")
    stats = camera.roi.stats1
    requested = threading.Event()
    original = stats.ts_acquire.callback

    def hold_ack(value):
        if value == 1:
            requested.set()
        else:
            original(value)

    stats.ts_acquire.callback = hold_ack
    staged = camera.stage()
    assert requested.wait(timeout=1)
    assert not staged.done
    assert camera.cam.acquire.get() == 0
    stats.ts_current_index.put(0)
    stats.ts_acquire_status.put(1)
    staged.wait(timeout=2)
    assert camera.cam.acquire.get() == 1


def test_stop_cancels_pending_roi_arming(camera):
    wait(camera.stage())
    stats = camera.roi.stats1
    requested = threading.Event()
    original = stats.ts_acquire.callback

    def hold_ack(value):
        if value == 1:
            requested.set()
        else:
            original(value)

    stats.ts_acquire.callback = hold_ack
    camera.writes.clear()
    trigger = camera.trigger()
    assert requested.wait(timeout=1)
    camera.stop()
    with pytest.raises(DeviceStoppedError):
        trigger.wait(timeout=2)
    assert ("acquire", 1) not in camera.writes
    assert camera.cam.acquire.get() == 0
    assert stats.ts_acquire_status.get() == 0


def test_preview_timer_cancels_a_sequence_of_slow_valid_reads(camera):
    from contextlib import ExitStack

    camera.io_timeout = 0.05
    camera.redis_update_frequency = 50
    entered = threading.Event()
    reads = [
        camera.image.unique_id,
        camera.image.array_size.width,
        camera.image.array_size.height,
        camera.image.array_size.depth,
        camera.image.color_mode,
        camera.image.array_data,
    ]
    with ExitStack() as stack:
        for signal in reads:
            original = signal.get

            def slow_read(*args, _get=original, **kwargs):
                entered.set()
                time.sleep(0.04)  # Each read meets its own 50 ms timeout.
                return _get(*args, **kwargs)

            stack.enter_context(mock.patch.object(signal, "get", side_effect=slow_read))
        publish = stack.enter_context(mock.patch.object(camera.preview, "put"))
        camera.start_live().wait(timeout=2)
        assert entered.wait(timeout=1)
        camera.stop_polling()
        assert not camera._poll_thread.is_alive()
        publish.assert_not_called()


def test_live_controls_are_exposed_through_bec_metadata(camera):
    from bec_server.device_server.devices.device_serializer import get_custom_user_access_info

    access = get_custom_user_access_info(camera, {})
    assert access["start_live"]["type"] == "func"
    assert access["stop_live"]["type"] == "func"


def test_camera_explicitly_initializes_rois_before_starting_live(camera):
    camera.stop_live(update_preference=False)
    with mock.patch.object(camera.roi, "on_connected") as connected:

        def check_input_stopped():
            assert camera.cam.acquire.get() == 0

        connected.side_effect = check_input_stopped
        camera.on_connected()
        connected.assert_called_once_with()
    assert camera.cam.acquire.get() == 1


@pytest.mark.parametrize("scan_type", ["software_triggered", "hardware_triggered"])
def test_monitored_acquisition_uses_bec_bursts_regardless_of_scan_type(camera, scan_type):
    priority = "monitored"
    set_scan(camera, priority, scan_type, software_trigger=True)
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
        wait(camera.stage())
        assert camera.cam.acquire.get() == 0
        assert camera.cam.array_counter.get() == 0
        camera.trigger().wait(timeout=2)
        assert result.call_count == camera.frames_per_trigger
        assert camera.measurement.get().metadata["correlation_group"] == priority
        camera.complete().wait(timeout=2)
        assert result.call_count == camera.frames_per_trigger


def test_external_async_uses_received_frames_in_a_software_scan(camera):
    camera.external_trigger_mode = VimbaTriggerMode.ON
    camera.acquisition_source.put("external")
    set_scan(camera, "async", software_trigger=False)
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
        wait(camera.stage())
        assert camera.cam.image_mode.get() == "Continuous"
        assert camera.cam.trigger_mode.get() == 1
        assert camera.cam.acquire.get() == 1
        camera.emit_frames(5)
        assert camera.cam.acquire.get() == 1
        camera.complete().wait(timeout=2)
        assert result.call_count == 5
        assert camera.measurement.get().metadata["correlation_group"] == "async"


def test_async_publishes_incrementally_up_to_fixed_buffer_capacity(camera):
    camera.async_frame_limit = 9
    set_scan(camera, "async", software_trigger=False)
    wait(camera.stage())
    arrived = threading.Event()
    target = [2]
    token = camera.measurement.subscribe(
        lambda *, value, **_: arrived.set() if value.metadata["frame_ids"] == target else None,
        run=False,
    )
    try:
        with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
            for last_frame in (2, 5, 8):
                target[:] = [last_frame]
                arrived.clear()
                camera.emit_frames(3)
                assert arrived.wait(timeout=2)
            camera.complete().wait(timeout=2)
            assert result.call_count == 9
            assert camera.roi._capture_offset == 9
            assert camera.cam.acquire.get() == 0
    finally:
        camera.measurement.unsubscribe(token)


@pytest.mark.parametrize("priority,software_trigger", [("monitored", False), ("async", True)])
def test_trigger_config_must_follow_readout_priority(camera, priority, software_trigger):
    """
    Reject unsupported cross-combinations before component configuration writes.
    """
    set_scan(camera, priority, software_trigger=software_trigger)
    camera._staged = Staged.yes
    before = list(camera.writes)
    with pytest.raises(ValueError, match="requires softwareTrigger"):
        camera.components.stage_camera()
    assert camera.writes == before


def test_baseline_does_not_reacquire_on_automatic_bec_triggers(camera):
    set_scan(camera, "baseline", software_trigger=True)
    wait(camera.stage())
    wait(camera.pre_scan())
    frames = camera.cam.array_counter.get()
    with mock.patch.object(camera.measurement, "put") as result:
        camera.trigger().wait(timeout=2)
        camera.read()
        assert camera.cam.array_counter.get() == frames
        result.assert_not_called()


def test_async_exceeding_fixed_capacity_stops_and_fails_scan(camera):
    camera.async_frame_limit = 4
    set_scan(camera, "async", software_trigger=False)
    wait(camera.stage())
    stopped = threading.Event()
    original = camera.stop

    def stop(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        finally:
            stopped.set()

    with mock.patch.object(camera, "stop", side_effect=stop):
        camera.emit_frames(5)
        assert stopped.wait(timeout=2)
    with pytest.raises(RuntimeError, match="buffer (capacity|overflow)"):
        camera.complete()
    assert camera.cam.acquire.get() == 0


def test_internal_acquisition_runs_until_complete_without_bec_triggers(camera):
    set_scan(camera, "async", software_trigger=False)
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
        wait(camera.stage())
        assert camera.cam.image_mode.get() == "Continuous"
        camera.emit_frames(4)
        assert camera.cam.acquire.get() == 1
        camera.complete().wait(timeout=2)
        assert camera.cam.acquire.get() == 0
        assert camera.cam.array_counter.get() == 4
        assert result.call_count == 4


def test_independent_unknown_count_does_not_require_monitored_readout_count(camera):
    set_scan(camera, "async", software_trigger=False)
    camera.scan_info.msg.num_monitored_readouts = 0
    camera.scan_info.msg.info["num_points"] = 0
    wait(camera.stage())
    assert camera.cam.image_mode.get() == "Continuous"
    camera.complete().wait(timeout=2)


@pytest.mark.parametrize("priority", ["monitored", "async"])
def test_acquisition_without_roi_components_completes(camera, priority):
    set_scan(camera, priority)
    with mock.patch.object(camera.components, "get_rois", return_value=[]):
        wait(camera.stage())
        if priority == "monitored":
            camera.trigger().wait(timeout=2)
        else:
            camera.emit_frames(3)
        camera.complete().wait(timeout=2)
        assert camera.cam.acquire.get() == 0
        assert camera.measurement.get() is None


@pytest.fixture
def hdf5_camera(camera, monkeypatch, tmp_path):
    """
    Attach an optional file plugin while keeping camera acquisition on real statuses.
    """
    camera.hdf5 = NS(
        **{
            name: PV(f"hdf5_{name}", value, camera.writes)
            for name, value in {
                "capture": 0,
                "enable": 0,
                "file_path": "",
                "file_name": "",
                "file_template": "",
                "file_write_mode": 0,
                "auto_increment": 1,
                "auto_save": 1,
                "lazy_open": 0,
                "num_capture": 1,
                "num_captured": 0,
                "array_size": (0, 2, 2),
                "array_counter": 1,
                "file_path_exists": 1,
                "write_file": 0,
                "write_status": 0,
                "write_message": "",
            }.items()
        }
    )
    for signal in vars(camera.hdf5).values():
        signal.put(signal.get())
    dimensions = camera.hdf5.array_size
    dimensions.width = PV("hdf5_width", 2, camera.writes)
    dimensions.callback = lambda value: dimensions.width.put(value[-1])
    camera.hdf5.capture.callback = lambda value: (
        camera.hdf5.num_captured.put(0) if value == 1 else None
    )
    monkeypatch.setattr(camera.file_event, "put", mock.Mock())
    camera.test_file_path = str(tmp_path / "scan_camera.h5")
    monkeypatch.setattr(
        camera.file_utils, "get_full_path", mock.Mock(return_value=camera.test_file_path)
    )
    yield camera
    camera.hdf5 = None


def test_hdf5_stage_and_complete_wait_for_queued_frames(hdf5_camera):
    """
    Arm one scan file before input and delay completion until its frames are written.
    """
    camera = hdf5_camera
    wait(camera.stage())
    camera.file_utils.get_full_path.assert_called_once_with(
        scan_status_msg=camera.scan_info.msg, name=camera.name, create_dir=False
    )
    assert camera.hdf5.file_template.get() == "%s%s"
    assert camera.hdf5.file_write_mode.get() == 2
    assert camera.hdf5.num_capture.get() == 0
    assert camera.hdf5.capture.get() == 1
    assert camera.file_event.put.call_args.kwargs["done"] is False
    camera.trigger().wait(timeout=2)
    camera.trigger().wait(timeout=2)
    completed = camera.complete()
    assert not completed.done
    assert camera.hdf5.capture.get() == 1
    assert camera.file_event.put.call_count == 1
    camera.hdf5.num_captured.put(6)
    completed.wait(timeout=2)
    assert camera.hdf5.capture.get() == 0
    assert camera.file_event.put.call_args.kwargs == {
        "file_path": camera.test_file_path,
        "done": True,
        "successful": True,
        "hinted_h5_entries": {"data": "/entry/data/data"},
    }
    wait(camera.unstage())
    assert camera.file_event.put.call_count == 2


def test_hdf5_unknown_length_independent_acquisition(hdf5_camera):
    """
    Open-ended async acquisition closes the file without a fixed-count contract.
    """
    camera = hdf5_camera
    camera.acquisition_source.put("internal")
    set_scan(camera, priority="async", software_trigger=False)
    wait(camera.stage())
    camera.emit_frames(4)
    camera.hdf5.num_captured.put(4)
    camera.complete().wait(timeout=2)
    assert camera.file_event.put.call_args.kwargs["successful"] is True
    names = [name for name, value in camera.writes]
    assert names.index("hdf5_file_path") < names.index(
        "hdf5_capture", names.index("hdf5_file_path")
    )
    assert next(i for i, pair in enumerate(camera.writes) if pair == ("hdf5_capture", 1)) < next(
        i for i, pair in enumerate(camera.writes) if pair == ("acquire", 1)
    )


@pytest.mark.parametrize("failure", ["write_error", "abort", "missing_frames", "empty"])
def test_hdf5_failures_do_not_announce_success(hdf5_camera, failure):
    """
    Failed writes, interrupted scans and missing data publish an unsuccessful event.
    """
    camera = hdf5_camera
    wait(camera.stage())
    if failure == "abort":
        camera.stop()
    else:
        if failure != "empty":
            camera.trigger().wait(timeout=2)
        if failure == "write_error":
            camera.hdf5.num_captured.put(3)
            camera.hdf5.write_status.put(1)
            camera.hdf5.write_message.put("Disk full")
        with pytest.raises((RuntimeError, TimeoutError)):
            camera.complete().wait(timeout=2)
    assert camera.hdf5.capture.get() == 0
    assert camera.file_event.put.call_args.kwargs["done"] is True
    assert camera.file_event.put.call_args.kwargs["successful"] is False


def test_hdf5_missing_ioc_directory_fails_before_input(hdf5_camera):
    """
    An unavailable IOC output directory prevents scan acquisition.
    """
    camera = hdf5_camera
    camera.hdf5.file_path_exists.put(0)
    with pytest.raises(RuntimeError, match="unavailable to the IOC"):
        camera.stage()
    assert camera.hdf5.capture.get() == 0
    assert camera.cam.acquire.get() == 0
    camera.file_event.put.assert_not_called()


def test_hdf5_complete_waits_for_pending_software_burst(hdf5_camera):
    """
    Completion during an outstanding burst still waits for the file to close.
    """
    camera = hdf5_camera
    camera.hold_camera = True
    wait(camera.stage())
    triggered = camera.trigger()
    completed = camera.complete()
    assert not completed.done
    assert camera.complete() is completed
    deadline = time.monotonic() + 1
    while not camera.cam.acquire.get() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert camera.cam.acquire.get() == 1
    camera.emit_frames(3)
    triggered.wait(timeout=2)
    assert not completed.done
    camera.hdf5.num_captured.put(3)
    completed.wait(timeout=2)
    assert camera.file_event.put.call_args.kwargs["successful"] is True


def test_hdf5_translates_only_ioc_path(hdf5_camera):
    """
    IOC paths use the remote mount; file events retain the filename BEC can read.
    """
    camera = hdf5_camera
    camera.hdf5_path_mapping = {str(Path(camera.test_file_path).parent): "/data"}
    wait(camera.stage())
    assert camera.hdf5.file_path.get() == "/data/"
    assert camera.hdf5.file_name.get() == "scan_camera.h5"
    assert camera.file_event.put.call_args.kwargs["file_path"] == camera.test_file_path
    camera.trigger().wait(timeout=2)
    camera.hdf5.num_captured.put(3)
    camera.complete().wait(timeout=2)
    assert camera.file_event.put.call_args.kwargs["file_path"] == camera.test_file_path


@pytest.mark.parametrize(
    "mapping,path,expected",
    [
        ({}, "/host/data/scan.h5", "/host/data/scan.h5"),
        ({"/host/data": "/data"}, "/host/data/scan/one.h5", "/data/scan/one.h5"),
        ({"/host": "/general", "/host/data": "/data"}, "/host/data/one.h5", "/data/one.h5"),
        ({"/host/data/": "/data/"}, "/host/data/one.h5", "/data/one.h5"),
    ],
)
def test_hdf5_directory_prefix_mapping(camera, mapping, path, expected):
    """
    Preserve subdirectories and prefer the longest matching directory prefix.
    """
    camera.hdf5_path_mapping = mapping
    assert camera.components.hdf5_ioc_path(path) == expected


@pytest.mark.parametrize(
    "mapping",
    [{"/host/data": "/data"}, {"relative": "/data"}, {"/host": "relative"}, {"/host": 42}],
)
def test_hdf5_invalid_or_unmatched_mapping_is_rejected(camera, mapping):
    """
    Reject malformed mappings and prefixes that match only part of a directory name.
    """
    camera.hdf5_path_mapping = mapping
    with pytest.raises((TypeError, ValueError)):
        camera.components.hdf5_ioc_path("/host/database/scan.h5")


@pytest.mark.parametrize("mode", list(AcquisitionSource))
def test_async_source_uses_shared_enum(camera, mode):
    """
    Async cameras select only internal clock or external hardware input.
    """
    camera.external_trigger_mode = VimbaTriggerMode.ON
    camera.acquisition_source.put(mode.value)
    set_scan(camera, "async")
    wait(camera.stage())
    assert camera.cam.image_mode.get() == "Continuous"
    assert camera.cam.trigger_mode.get() == (
        camera.external_trigger_mode.value
        if mode == AcquisitionSource.EXTERNAL
        else camera.internal_trigger_mode.value
    )
    assert camera.cam.acquire.get() == 1
    camera.complete().wait(timeout=2)


@pytest.mark.parametrize("mode", ["auto", "software", "continuous", "invalid"])
def test_invalid_async_acquisition_source_is_rejected(camera, mode):
    """
    Reject removed or unsupported source settings before starting async input.
    """
    camera.acquisition_source.put(mode)
    set_scan(camera, "async")
    with pytest.raises(ValueError):
        wait(camera.stage())


@pytest.mark.parametrize("priority", ["baseline", "monitored"])
def test_triggered_priorities_ignore_async_source_setting(camera, priority):
    """
    Selecting an async source does not change baseline or monitored burst behavior.
    """
    camera.acquisition_source.put("external")
    set_scan(camera, priority)
    wait(camera.stage())
    assert camera.cam.image_mode.get() == "Multiple"
    assert camera.cam.trigger_mode.get() == camera.internal_trigger_mode.value
    if priority == "monitored":
        camera.trigger().wait(timeout=2)
    else:
        wait(camera.pre_scan())
    assert camera.cam.array_counter.get() == camera.frames_per_trigger


def test_trigger_mode_mappings_are_enums_but_pv_writes_are_integers(camera):
    """
    Keep driver enum mappings readable while sending their integer values to EPICS.
    """
    from enum import IntEnum

    assert isinstance(camera.internal_trigger_mode, IntEnum)
    camera.cam.trigger_mode.put(VimbaTriggerMode.ON.value)
    camera.writes.clear()
    wait(camera.stage())
    camera.trigger().wait(timeout=2)
    camera.complete().wait(timeout=2)
    wait(camera.unstage())
    values = [value for name, value in camera.writes if name == "trigger_mode"]
    assert values
    assert all(type(value) is int for value in values)
    assert all(value == camera.internal_trigger_mode.value for value in values)


def test_repeated_camera_setup_rewrites_configuration(camera):
    """
    Reapplying a setup writes every setting without trusting the monitor cache.
    """
    wait(camera.stage())
    camera.writes.clear()
    camera.components.stage_camera()
    settings = {
        "acquire_time",
        "acquire_period",
        "num_images",
        "image_mode",
        "trigger_mode",
        "array_callbacks",
        "image_enable",
    }
    assert settings <= {name for name, value in camera.writes}
    assert ("acquire", 0) in camera.writes
    camera.trigger().wait(timeout=2)
    camera.trigger().wait(timeout=2)
    assert camera.cam.array_counter.get() == 2 * camera.frames_per_trigger


def test_repeated_roi_arming_writes_settings_and_resets_capture(camera):
    """
    Each burst explicitly writes time-series settings and resets capture.
    """
    wait(camera.stage())
    camera.trigger().wait(timeout=2)
    camera.writes.clear()
    camera.trigger().wait(timeout=2)
    assert {"ts_acquire_mode", "ts_read_mode", "ts_num_points"} <= {
        name for name, value in camera.writes
    }
    assert ("ts_acquire", 1) in camera.writes
    assert ("ts_read", 1) in camera.writes
    assert camera.cam.array_counter.get() == 2 * camera.frames_per_trigger


def test_disabling_frame_saving_keeps_roi_publication(hdf5_camera):
    """
    An installed HDF5 plugin does not imply frame saving; ROI data still streams.
    """
    camera = hdf5_camera
    camera.save_frame_data.put(False)
    wait(camera.stage())
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
        camera.trigger().wait(timeout=2)
        camera.complete().wait(timeout=2)
        assert result.call_count == camera.frames_per_trigger
    assert camera.hdf5.capture.get() == 0
    assert ("hdf5_capture", 1) not in camera.writes
    camera.file_utils.get_full_path.assert_not_called()
    camera.file_event.put.assert_not_called()


def test_disabling_frame_saving_during_capture_still_closes_the_file(hdf5_camera):
    """
    A changed preference takes effect on the next stage, not during active file writing.
    """
    camera = hdf5_camera
    wait(camera.stage())
    camera.save_frame_data.put(False)
    camera.trigger().wait(timeout=2)
    camera.hdf5.num_captured.put(camera.frames_per_trigger)
    camera.complete().wait(timeout=2)
    assert camera.file_event.put.call_args.kwargs["successful"] is True
    assert camera.hdf5.capture.get() == 0


def test_unsaved_roi_results_keep_streaming_to_bec(camera):
    """
    signal_info.saved controls file persistence, not dynamic-signal publication.
    """
    camera.measurement.signal_info.saved = False
    wait(camera.stage())
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
        camera.trigger().wait(timeout=2)
        camera.complete().wait(timeout=2)
        assert result.call_count == camera.frames_per_trigger
    assert camera.measurement.get().signals
    assert not camera.measurement.describe()[camera.measurement.name]["signal_info"]["saved"]


def test_cold_hdf5_primes_before_scan_capture(hdf5_camera):
    """
    Wait for the unsaved frame and idle acknowledgement before arming the scan file.
    """
    camera = hdf5_camera
    camera.hdf5.array_size.put((0, 0, 0))
    camera.cam.trigger_mode.put(1)
    camera.cam.num_images.put(7)
    camera.live_enabled.put(False)
    original_exposure = camera.cam.acquire_time.get()
    camera.writes.clear()
    with (
        mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as publish,
        staging_during_priming(camera) as staged,
    ):
        assert not staged.done()
        assert camera.cam.image_mode.get() == "Single"
        assert camera.cam.trigger_mode.get() == camera.internal_trigger_mode.value
        assert camera.hdf5.enable.get() == 1
        assert camera.hdf5.capture.get() == 0
        assert camera.hdf5.auto_save.get() == 0
        camera.file_event.put.assert_not_called()
        camera.cam.array_counter.put(1)
        camera.hdf5.array_size.put((0, 2, 2))
        # Receipt alone is insufficient: the camera must also finish the exposure.
        assert not staged.done()
        camera.cam.acquire.put(0)
        wait(staged.result(timeout=2))
        assert publish.call_count == 0
    assert camera._frame_origin == 1
    assert camera.hdf5.capture.get() == 1
    assert camera.cam.image_mode.get() == "Multiple"
    assert camera.cam.num_images.get() == 3
    assert not camera.live_enabled.get()
    # Restoration precedes application of scan settings and the first scan file.
    writes = camera.writes
    arm = writes.index(("hdf5_capture", 1))
    assert writes.index(("trigger_mode", 1)) < arm
    assert writes.index(("hdf5_auto_save", 1)) < arm
    assert original_exposure != camera.cam.acquire_time.get()


def test_cold_hdf5_disabled_saving_needs_no_priming(hdf5_camera):
    """
    ROI-only staging neither waits for plugin dimensions nor acquires a frame.
    """
    camera = hdf5_camera
    camera.hdf5.array_size.put((0, 0, 0))
    camera.save_frame_data.put(False)
    camera.writes.clear()
    wait(camera.stage())
    assert ("acquire", 1) not in camera.writes
    assert camera.hdf5.array_size.get() == (0, 0, 0)
    camera.file_event.put.assert_not_called()


@pytest.mark.parametrize("failure", ["timeout", "stop", "acquire_error"])
def test_hdf5_priming_failure_restores_settings(hdf5_camera, failure):
    """
    Failed or interrupted priming stops input, restores settings and creates no file.
    """
    camera = hdf5_camera
    camera.acquisition_timeout = 1 if failure == "stop" else 0.05
    camera.hdf5.array_size.put((0, 0, 0))
    camera.cam.trigger_mode.put(1)
    if failure == "acquire_error":

        def fail_acquire(value):
            if value == 1:
                raise RuntimeError("Cannot acquire internally")

        camera.cam.acquire.callback = fail_acquire
    with staging_during_priming(camera) as staged:
        if failure == "stop":
            camera.stop()
        with pytest.raises((TimeoutError, DeviceStoppedError, RuntimeError)):
            staged.result(timeout=2)
    assert camera.cam.acquire.get() == 0
    assert camera.cam.image_mode.get() == "Continuous"
    assert camera.cam.trigger_mode.get() == 1
    assert camera.hdf5.enable.get() == 0
    assert camera.hdf5.auto_save.get() == 1
    assert camera.hdf5.capture.get() == 0
    assert ("hdf5_capture", 1) not in camera.writes
    camera.file_event.put.assert_not_called()


@pytest.mark.parametrize("priority", ["baseline", "async"])
def test_priming_continues_the_selected_scan_lifecycle(hdf5_camera, priority):
    """
    Blocking priming precedes independent startup; baseline waits for pre_scan.
    """
    camera = hdf5_camera
    set_scan(camera, priority)
    camera.hdf5.array_size.put((0, 0, 0))
    with (
        mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as publish,
        staging_during_priming(camera) as staged,
    ):
        assert not staged.done()
        camera.cam.array_counter.put(1)
        camera.hdf5.array_size.put((0, 2, 2))
        camera.cam.acquire.put(0)
        wait(staged.result(timeout=2))
        assert publish.call_count == 0
        if priority == "baseline":
            wait(camera.pre_scan())
            assert publish.call_count == 1
    assert camera._frame_origin == 1
    assert camera.cam.acquire.get() == (0 if priority == "baseline" else 1)
    assert camera.hdf5.capture.get() == 1


@pytest.mark.parametrize("waveform", ["ts_sum", "ts_timestamp"])
@pytest.mark.parametrize("priority", ["monitored", "async"])
def test_capture_rejects_waveform_capacity_below_requested_buffer(camera, waveform, priority):
    """
    NELM limits finite bursts and the total async scan, including their timestamps.
    """
    set_scan(camera, priority)
    camera.async_frame_limit = 3
    getattr(camera.roi.stats1, waveform)._read_pv.nelm = 2
    if priority == "monitored":
        wait(camera.stage())
        operation = camera.trigger()
    else:
        operation = camera.stage()
    with pytest.raises(ValueError, match=f"{waveform} supports 2 elements, requested 3"):
        wait(operation)
    assert ("acquire", 1) not in camera.writes
    assert camera.cam.acquire.get() == 0


@pytest.mark.parametrize("priority", ["monitored", "async"])
def test_capture_disables_ioc_time_series_averaging(camera, priority):
    """
    A caQtDM averaging setting is reset before capture, preserving one sample per frame.
    """
    stats = camera.roi.stats1
    stats.ts_averaging_time.put(0.4)
    stats.ts_num_average.put(4)
    stats.ts_averaging_time.callback = lambda value: stats.ts_num_average.put(
        1 if value == 0 else 4
    )
    set_scan(camera, priority)
    wait(camera.stage())
    if priority == "monitored":
        wait(camera.trigger())
    else:
        camera.emit_frames(2)
        wait(camera.complete())
    assert stats.ts_averaging_time.get() == 0
    assert stats.ts_num_average.get() == 1
    assert camera.writes.index(("ts_averaging_time", 0)) < camera.writes.index(("ts_acquire", 1))
    assert camera.measurement.get().signals


def test_async_scan_preserves_manual_burst_for_next_monitored_scan(camera):
    """
    Continuous acquisition leaves NumImages unchanged for later manually timed bursts.
    """
    camera.live_enabled.put(False)
    camera.use_scan_timing.put(False)
    camera.cam.num_images.put(7)
    camera.cam.acquire_time.put(0.03)
    camera.cam.acquire_period.put(0.04)
    camera.writes.clear()
    set_scan(camera, "async")
    wait(camera.stage())
    wait(camera.complete())
    wait(camera.unstage())
    assert camera.cam.num_images.get() == 7
    assert not any(name == "num_images" for name, _ in camera.writes)
    set_scan(camera, "monitored")
    wait(camera.stage())
    assert camera.frames_per_trigger == 7
    assert camera.cam.num_images.get() == 7


def test_baseline_pre_scan_waits_for_roi_drain_before_ready(camera):
    """
    Staging acquires no baseline data; pre_scan waits for delayed ROI publication.
    """
    set_scan(camera, "baseline")
    camera.delay_stats = True
    wait(camera.stage())
    assert camera.cam.array_counter.get() == 0
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as publish:
        ready = camera.pre_scan()
        assert not ready.done
        ready.wait(timeout=2)
        assert publish.call_count == 1
    assert camera.cam.array_counter.get() == camera.frames_per_trigger
    assert camera.measurement.get().metadata["correlation_group"] == "baseline"


@pytest.mark.parametrize("waveform", ["ts_sum", "ts_timestamp"])
def test_async_default_capacity_uses_smallest_selected_waveform(camera, waveform):
    """
    Discover the IOC limit from waveform NELM without requiring camera configuration.
    """
    set_scan(camera, "async", software_trigger=False)
    getattr(camera.roi.stats1, waveform)._read_pv.nelm = 7
    wait(camera.stage())
    assert camera.roi.stats1.ts_num_points.get() == 7
    assert camera.roi.stats1.ts_acquire_mode.get() == 0
    camera.emit_frames(7)
    camera.complete().wait(timeout=2)
    assert camera.roi._capture_offset == 7


def test_async_roi_limit_does_not_apply_without_selected_outputs(camera):
    """
    Disabling ROI outputs permits acquisitions beyond the optional ROI scan limit.
    """
    camera.async_frame_limit = 2
    camera.roi.selected_operations.put([])
    set_scan(camera, "async", software_trigger=False)
    wait(camera.stage())
    camera.emit_frames(8)
    camera.complete().wait(timeout=2)
    assert camera.measurement.get() is None
    assert camera.components._stream_limit_status is None


@pytest.mark.parametrize("short_waveform", ["ts_sum", "ts_timestamp"])
def test_fixed_roi_publishes_common_prefix_while_waveforms_catch_up(camera, short_waveform):
    """
    Unequal waveform lengths preserve sample positions and never block publication.
    """
    roi, stats = camera.roi, camera.roi.stats1
    roi._capture_outputs = {"sum": "ts_sum"}
    roi._capture_armed = True
    stats.ts_current_index.put(4)
    stats.ts_sum.put(np.arange(4, dtype=float))
    stats.ts_timestamp.put(np.arange(4, dtype=float) + 1000)
    short = getattr(stats, short_waveform)
    complete = short.get().copy()
    short.put(complete[:3])
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as result:
        roi.publish_capture(camera=camera, source_path="roi", group="async", frame_origin=0)
        assert roi._capture_offset == 3
        assert result.call_count == 3
        short.put(complete)
        roi.publish_capture(camera=camera, source_path="roi", group="async", frame_origin=0)
        assert roi._capture_offset == 4
        assert result.call_count == 4
        assert [call.kwargs["metadata"]["frame_ids"] for call in result.call_args_list] == [
            [0],
            [1],
            [2],
            [3],
        ]


def test_fixed_roi_publishes_when_input_advances_during_tsread(camera):
    """
    A moving input counter cannot starve fixed-buffer publication.
    """
    roi, stats = camera.roi, camera.roi.stats1
    roi._capture_outputs = {"sum": "ts_sum"}
    roi._capture_armed = True
    stats.ts_current_index.put(3)
    stats.ts_sum.put(np.arange(3, dtype=float))
    stats.ts_timestamp.put(np.arange(3, dtype=float) + 1000)

    def more_input(value):
        stats.ts_sum.put(np.arange(4, dtype=float))
        stats.ts_timestamp.put(np.arange(4, dtype=float) + 1000)
        stats.ts_current_index.put(4)
        stats.ts_array_counter.put(4)

    stats.ts_read.callback = more_input
    roi.publish_capture(camera=camera, source_path="roi", group="async", frame_origin=0)
    assert roi._capture_offset == 3
    roi.publish_capture(camera=camera, source_path="roi", group="async", frame_origin=0)
    assert roi._capture_offset == 4


def test_fixed_final_read_rejects_missing_waveform_samples(camera):
    """
    Completion must not silently omit samples still missing from a waveform.
    """
    roi, stats = camera.roi, camera.roi.stats1
    roi._capture_outputs = {"sum": "ts_sum"}
    stats.ts_current_index.put(3)
    stats.ts_sum.put(np.arange(2, dtype=float))
    stats.ts_timestamp.put(np.arange(3, dtype=float) + 1000)
    with pytest.raises(RuntimeError, match="Incomplete ROI time series"):
        roi.publish_capture(camera=camera, source_path="roi", group="async", frame_origin=0)


@pytest.mark.parametrize("fails", [False, True])
def test_hdf5_priming_uses_short_timing_and_restores_previous_exposure(hdf5_camera, fails):
    """
    A previous long exposure cannot delay the unsaved frame or replace user timing.
    """
    camera = hdf5_camera
    camera.hdf5.array_size.put((0, 0, 0))
    camera.cam.acquire_time.put(120)
    camera.cam.acquire_period.put(180)
    attempts = []

    def acquire(value):
        if value != 1:
            return
        attempts.append(value)
        assert camera.cam.acquire_time.get() == 0.01
        assert camera.cam.acquire_period.get() == 0.01
        assert camera.hdf5.capture.get() == 0
        if fails:
            raise RuntimeError("priming acquisition failed")
        camera.hdf5.array_size.put((0, 2, 2))
        camera.cam.acquire.put(0)

    camera.cam.acquire.callback = acquire
    if fails:
        with pytest.raises(RuntimeError, match="priming acquisition failed"):
            camera.components.prime_hdf5()
    else:
        camera.components.prime_hdf5()
    assert attempts == [1]
    assert camera.cam.acquire_time.get() == 120
    assert camera.cam.acquire_period.get() == 180
    assert camera.cam.acquire.get() == 0
    camera.file_event.put.assert_not_called()


def test_hdf5_stage_waits_for_reset_and_completion_ignores_previous_cached_count(hdf5_camera):
    """
    Delayed previous-file readbacks cannot arm input or prematurely close a new file.
    """
    camera = hdf5_camera

    class DelayedCounter(PV):
        def __init__(self):
            super().__init__("captured", 99, camera.writes)
            self.actual = 99

        def get(self, *, use_monitor=True, **kwargs):
            return super().get(**kwargs) if use_monitor else self.actual

    counter = DelayedCounter()
    camera.hdf5.num_captured = counter
    armed = threading.Event()

    def capture(value):
        if value == 1:
            counter.actual = 0
            armed.set()

    camera.hdf5.capture.callback = capture
    with ThreadPoolExecutor(max_workers=1) as pool:
        staged = pool.submit(camera.stage)
        assert armed.wait(timeout=1)
        assert not staged.done()
        assert camera.cam.acquire.get() == 0
        counter.put(0)  # Delivery of the current capture's reset notification.
        wait(staged.result(timeout=2))
    camera.trigger().wait(timeout=2)
    # Independently exercise completion's explicit read, rather than run=True cache use.
    counter.put(99)
    completed = camera.complete()
    assert not completed.done
    assert camera.hdf5.capture.get() == 1
    assert camera.file_event.put.call_args.kwargs["done"] is False
    counter.actual = 3
    counter.put(3)
    completed.wait(timeout=2)
    assert camera.file_event.put.call_args.kwargs["successful"] is True


def test_hdf5_missing_counter_reset_fails_before_camera_input(hdf5_camera):
    """
    A capture that never resets cannot start input or leave a pending file armed.
    """
    camera = hdf5_camera
    camera.io_timeout = 0.05
    camera.hdf5.num_captured.put(99)
    camera.hdf5.capture.callback = None
    with pytest.raises(TimeoutError, match="counter reset"):
        camera.stage()
    assert camera.cam.acquire.get() == 0
    assert camera.hdf5.capture.get() == 0
    assert camera.file_event.put.call_args.kwargs["done"] is True
    assert camera.file_event.put.call_args.kwargs["successful"] is False


def test_live_restore_writes_even_if_monitor_cache_matches_requested_timing(camera):
    """
    A delayed pre-scan readback must not suppress restoration of actual controller PVs.
    """
    camera.cam.acquire_time.put(1.2)
    camera.cam.acquire_period.put(1.3)
    camera.live_follows_scan_timing.put(False)
    wait(camera.stage())
    camera.trigger().wait(timeout=2)
    camera.complete().wait(timeout=2)
    assert camera.cam.acquire_time.get() != 1.2
    actual_get = camera.cam.acquire_time.get

    def delayed_readback(*args, use_monitor=True, **kwargs):
        return 1.2 if use_monitor else actual_get(*args, **kwargs)

    camera.writes.clear()
    with mock.patch.object(camera.cam.acquire_time, "get", side_effect=delayed_readback):
        wait(camera.unstage())
    assert ("acquire_time", 1.2) in camera.writes
    assert ("acquire_period", 1.3) in camera.writes
    assert camera.cam.acquire_time.get() == 1.2
    assert camera.cam.acquire_period.get() == 1.3


def test_async_stop_during_start_status_registration_cannot_restart_input(camera):
    """
    Synchronous cancellation of startup must prevent the subsequent Acquire command.
    """
    set_scan(camera, "async", software_trigger=False)
    original = camera.cancel_on_stop
    stopped = []

    def stop_after_registration(status):
        original(status)
        if getattr(status, "obj", None) is camera.cam.acquire and not stopped:
            stopped.append(True)
            camera.stop()

    with (
        mock.patch.object(camera, "cancel_on_stop", side_effect=stop_after_registration),
        pytest.raises(DeviceStoppedError),
    ):
        wait(camera.stage())
    assert stopped == [True]
    assert camera.stopped
    assert camera.cam.acquire.get() == 0
    assert ("acquire", 1) not in camera.writes
    assert camera.roi.stats1.ts_acquire_status.get() == 0


def test_concurrent_async_stop_finishes_after_inflight_start_write(camera):
    """
    Stop waits for an in-flight start write, then leaves input and ROI capture stopped.
    """
    set_scan(camera, "async", software_trigger=False)
    writing = threading.Event()
    release = threading.Event()
    stopping = threading.Event()
    original_put = camera.cam.acquire.put
    original_stop = camera.on_stop

    def hold_start(value, **kwargs):
        if value == 1:
            writing.set()
            assert release.wait(timeout=2)
        return original_put(value, **kwargs)

    def announce_stop():
        camera.stopped = True
        stopping.set()
        original_stop()

    with (
        mock.patch.object(camera.cam.acquire, "put", side_effect=hold_start),
        mock.patch.object(camera, "on_stop", side_effect=announce_stop),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        staged = pool.submit(camera.stage)
        assert writing.wait(timeout=2)
        stopped = pool.submit(camera.stop)
        assert stopping.wait(timeout=2)
        try:
            assert not stopped.done()
        finally:
            release.set()
        stopped.result(timeout=2)
        with pytest.raises(DeviceStoppedError):
            wait(staged.result(timeout=2))
    writes = [value for name, value in camera.writes if name == "acquire"]
    assert 1 in writes
    assert writes[-1] == 0
    assert camera.cam.acquire.get() == 0
    assert camera.roi.stats1.ts_acquire_status.get() == 0


def test_cancelled_stream_callback_preserves_original_acquisition_error(camera):
    """
    A callback interrupted by stop must not replace the failure that caused the stop.
    """
    set_scan(camera, "async", software_trigger=False)
    wait(camera.stage())
    failure = RuntimeError("original acquisition failure")
    camera.components._stream_error = failure
    camera.stopped = True
    stopped = threading.Event()
    original = camera.stop

    def stop():
        try:
            original()
        finally:
            stopped.set()

    with mock.patch.object(camera, "stop", side_effect=stop):
        camera.emit_frames(1)
        assert stopped.wait(timeout=2)
    assert camera.components._stream_error is failure
    with pytest.raises(RuntimeError, match="original acquisition failure"):
        camera.complete()


@pytest.mark.parametrize("first_empty", ["ts_sum", "ts_timestamp"])
def test_roi_waits_for_all_empty_waveforms_before_starting_new_burst(camera, first_empty):
    """
    Previous equal-length data cannot become new scan results while reset PVs lag.
    """
    stats = camera.roi.stats1
    wait(camera.stage())
    stats.ts_sum.put(np.array([100.0, 101.0, 102.0]))
    stats.ts_timestamp.put(np.array([900.0, 901.0, 902.0]))
    requested = threading.Event()
    stats.ts_read.callback = lambda value: requested.set()
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as results:
        operation = camera.trigger()
        assert requested.wait(timeout=1)
        assert not operation.done
        assert camera.cam.acquire.get() == 0
        assert camera.cam.array_counter.get() == 0
        assert not camera.roi._capture_armed
        getattr(stats, first_empty).put(np.array([]))
        assert not operation.done
        assert camera.cam.array_counter.get() == 0
        remaining = "ts_timestamp" if first_empty == "ts_sum" else "ts_sum"
        getattr(stats, remaining).put(np.array([]))
        operation.wait(timeout=2)
    values = [next(iter(call.args[0].values()))["value"] for call in results.call_args_list]
    assert values == [0.0, 1.0, 2.0]
    assert camera.cam.array_counter.get() == 3


def test_empty_roi_waveforms_need_no_repeated_monitor_notification(camera):
    """
    Fresh reads acknowledge records already empty when no new monitor event arrives.
    """
    wait(camera.stage())
    camera.roi.stats1.ts_read.callback = None
    camera.trigger().wait(timeout=2)
    assert camera.cam.array_counter.get() == 3
    assert camera.roi._capture_offset == 3


def test_missing_empty_roi_acknowledgement_fails_before_camera_input(camera):
    """
    Missing resets time out, stop Stats capture and release waveform subscriptions.
    """
    camera.io_timeout = 0.05
    wait(camera.stage())
    stats = camera.roi.stats1
    stats.ts_sum.put(np.ones(3))
    stats.ts_timestamp.put(np.arange(3) + 1000)
    stats.ts_read.callback = None
    with pytest.raises(TimeoutError):
        camera.trigger().wait(timeout=2)
    assert camera.cam.array_counter.get() == 0
    assert ("acquire", 1) not in camera.writes
    assert stats.ts_acquire_status.get() == 0
    for signal in (stats.ts_sum, stats.ts_timestamp):
        assert not signal._callbacks[signal.SUB_VALUE]


@pytest.mark.parametrize("interrupt", ["stop", "destroy"])
def test_interrupt_pending_empty_roi_reset_never_starts_camera(camera, interrupt):
    """
    Both interruption paths cancel the empty-baseline wait and remove subscriptions.
    """
    wait(camera.stage())
    stats = camera.roi.stats1
    stats.ts_sum.put(np.ones(3))
    stats.ts_timestamp.put(np.arange(3) + 1000)
    requested = threading.Event()
    stats.ts_read.callback = lambda value: requested.set()
    operation = camera.trigger()
    assert requested.wait(timeout=1)
    getattr(camera, interrupt)()
    with pytest.raises(DeviceStoppedError):
        operation.wait(timeout=2)
    assert camera.cam.array_counter.get() == 0
    assert camera.cam.acquire.get() == 0
    for signal in (stats.ts_sum, stats.ts_timestamp):
        assert not signal._callbacks[signal.SUB_VALUE]


def test_repeated_equal_length_constant_bursts_publish_current_timestamps(camera):
    """
    Identical statistic values still belong to distinct, freshly armed captures.
    """
    wait(camera.stage())
    stats = camera.roi.stats1

    def acquire(value):
        if value != 1:
            return
        start = int(camera.cam.array_counter.get())
        stats.ts_sum.put(np.full(3, 7.0))
        stats.ts_timestamp.put(np.arange(3) + 1000 + start)
        stats.ts_current_index.put(3)
        camera.cam.array_counter.put(start + 3)
        camera.cam.acquire.put(0)

    camera.cam.acquire.callback = acquire
    with mock.patch.object(camera.measurement, "put", wraps=camera.measurement.put) as results:
        camera.trigger().wait(timeout=2)
        camera.trigger().wait(timeout=2)
    readings = [next(iter(call.args[0].values())) for call in results.call_args_list]
    assert [reading["value"] for reading in readings] == [7.0] * 6
    assert [reading["timestamp"] for reading in readings] == [
        631152000.0 + 1000 + index for index in range(6)
    ]


def test_hdf5_final_count_uses_ioc_value_when_monitor_still_reads_zero(hdf5_camera):
    """
    Current frames already written must not be rejected because their monitor is late.
    """
    camera = hdf5_camera
    wait(camera.stage())
    camera.trigger().wait(timeout=2)
    assert camera.hdf5.num_captured.get() == 0

    def count(*, use_monitor=True, **kwargs):
        return 0 if use_monitor else 3

    with mock.patch.object(camera.hdf5.num_captured, "get", side_effect=count):
        camera.complete().wait(timeout=2)
    assert camera.file_event.put.call_args.kwargs["successful"] is True


@pytest.mark.parametrize("cached,actual", [(0, 1), (1, 0)])
def test_hdf5_final_writer_status_and_message_use_fresh_readbacks(hdf5_camera, cached, actual):
    """
    Final success or failure follows the IOC state, including its current error text.
    """
    camera = hdf5_camera
    wait(camera.stage())
    camera.trigger().wait(timeout=2)
    camera.hdf5.num_captured.put(3)

    def status(*, use_monitor=True, **kwargs):
        return cached if use_monitor else actual

    def message(*, use_monitor=True, **kwargs):
        return "previous file error" if use_monitor else "current disk full"

    with (
        mock.patch.object(camera.hdf5.write_status, "get", side_effect=status),
        mock.patch.object(camera.hdf5.write_message, "get", side_effect=message),
    ):
        if actual:
            with pytest.raises(RuntimeError, match="HDF5 write failed: current disk full"):
                camera.complete().wait(timeout=2)
        else:
            camera.complete().wait(timeout=2)
    assert camera.file_event.put.call_args.kwargs["successful"] is (actual == 0)


def test_hdf5_final_count_must_still_cover_all_accepted_frames(hdf5_camera):
    """
    Recheck the count after closure instead of trusting a previous sufficient count.
    """
    camera = hdf5_camera
    wait(camera.stage())
    camera.trigger().wait(timeout=2)
    camera.hdf5.num_captured.put(3)
    camera.hdf5.capture.callback = lambda value: (
        camera.hdf5.num_captured.put(2) if value == 0 else None
    )
    with pytest.raises(RuntimeError, match="captured 2 frames, expected at least 3"):
        camera.complete().wait(timeout=2)
    assert camera.file_event.put.call_args.kwargs["successful"] is False


def test_hdf5_final_status_read_failure_reports_unsuccessful_file(hdf5_camera):
    """
    An unavailable fresh writer status cannot silently fall back to cached success.
    """
    camera = hdf5_camera
    wait(camera.stage())
    camera.trigger().wait(timeout=2)
    camera.hdf5.num_captured.put(3)
    original = camera.hdf5.write_status.get

    def unreadable_status(*, use_monitor=True, **kwargs):
        if not use_monitor:
            raise TimeoutError("final writer status unavailable")
        return original(**kwargs)

    with (
        mock.patch.object(camera.hdf5.write_status, "get", side_effect=unreadable_status),
        pytest.raises(TimeoutError, match="final writer status unavailable"),
    ):
        camera.complete().wait(timeout=2)
    assert camera.file_event.put.call_args.kwargs["successful"] is False


def test_runtime_redis_preview_enable_disable_preserves_live_acquisition(camera):
    """
    Runtime frequency changes manage only previews and leave camera input running.
    """
    polled = threading.Event()
    camera._preview_transports["preview"] = [
        {
            "transport": "zmq",
            "address": "tcp://ioc.example:5555",
            "socket_type": "sub",
            "connection_mode": "connect",
            "encoder": "array-1.0",
        }
    ]
    camera._configure_preview_transports(["preview", "roi.preview"])
    with (
        mock.patch.object(camera, "on_poll", side_effect=lambda: polled.set()),
        mock.patch.object(camera, "stop", wraps=camera.stop) as stop,
    ):
        assert camera._live_active
        assert camera.cam.acquire.get() == 1
        camera.redis_update_frequency = 100
        assert polled.wait(timeout=1)
        worker = camera._poll_thread
        assert any(t.transport == "redis" for t in camera.preview.signal_info.transports)
        assert any(t.transport == "redis" for t in camera.roi.preview.signal_info.transports)
        camera.redis_update_frequency = 0
        assert not worker.is_alive()
        assert camera._live_active
        assert camera.cam.acquire.get() == 1
        stop.assert_not_called()
        assert [t.transport for t in camera.preview.signal_info.transports] == ["zmq"]
        assert camera.roi.preview.signal_info.transports == []
        polled.clear()
        camera.redis_update_frequency = 100
        assert polled.wait(timeout=1)
        assert camera._poll_thread is not worker
        camera.redis_update_frequency = 50
        assert [t.transport for t in camera.preview.signal_info.transports] == ["zmq", "redis"]
        assert len(camera.roi.preview.signal_info.transports) == 1
        assert camera.cam.acquire.get() == 1
        stop.assert_not_called()
        camera.redis_update_frequency = 0


@pytest.mark.parametrize("frequency", [-1, float("nan"), float("inf"), None])
def test_invalid_runtime_preview_frequency_keeps_current_timer_and_live(camera, frequency):
    """
    Reject invalid runtime values before changing an active preview timer.
    """
    with mock.patch.object(camera, "on_poll"):
        camera.redis_update_frequency = 100
        worker = camera._poll_thread
        with pytest.raises(ValueError, match="redis_update_frequency"):
            camera.redis_update_frequency = frequency
        assert camera.redis_update_frequency == 100
        assert camera._poll_thread is worker
        assert worker.is_alive()
        assert camera.cam.acquire.get() == 1
        camera.redis_update_frequency = 0


def test_runtime_preview_frequency_during_scan_defers_timer_until_live_resumes(camera):
    """
    Changing preview settings must not start preview reads during scan acquisition.
    """
    wait(camera.stage())
    camera.redis_update_frequency = 100
    assert camera._poll_thread is None or not camera._poll_thread.is_alive()
    polled = threading.Event()
    with mock.patch.object(camera, "on_poll", side_effect=lambda: polled.set()):
        camera.trigger().wait(timeout=2)
        camera.complete().wait(timeout=2)
        wait(camera.unstage())
        assert polled.wait(timeout=1)
        camera.redis_update_frequency = 0
    assert camera.cam.acquire.get() == 1


def test_preview_callback_can_disable_redis_without_stopping_live(camera):
    """
    A timer callback can disable its own updates without joining itself or dividing by zero.
    """
    disabled = threading.Event()

    def disable():
        camera.redis_update_frequency = 0
        disabled.set()

    with mock.patch.object(camera, "on_poll", side_effect=disable):
        camera.redis_update_frequency = 100
        assert disabled.wait(timeout=1)
        camera._poll_thread.join(timeout=1)
    assert not camera._poll_thread.is_alive()
    assert camera.cam.acquire.get() == 1
    assert camera._live_active


@pytest.mark.parametrize("failure", ["raise", "failed_status", "pending_status"])
def test_failed_live_shutdown_can_be_retried(camera, failure):
    """
    Failed or pending shutdown must not be mistaken for successfully stopped live input.
    """
    wait(camera.start_live())
    original = camera.on_live_mode_stops
    status = ad_components.StatusBase()
    if failure == "failed_status":
        status.set_exception(TimeoutError("shutdown failed"))
    with mock.patch.object(camera, "on_live_mode_stops") as stop_hook:
        if failure == "raise":
            stop_hook.side_effect = TimeoutError("shutdown failed")
            with pytest.raises(TimeoutError, match="shutdown failed"):
                camera.stop_live()
        else:
            stop_hook.return_value = status
            returned = camera.stop_live()
            assert camera._live_active
            if failure == "pending_status":
                status.set_exception(TimeoutError("shutdown failed"))
            with pytest.raises(TimeoutError, match="shutdown failed"):
                returned.wait(timeout=1)
        assert camera._live_active
        assert camera.cam.acquire.get() == 1
        stop_hook.side_effect = None
        stop_hook.side_effect = original
        wait(camera.stop_live())
        assert stop_hook.call_count == 2
    assert not camera._live_active
    assert camera.cam.acquire.get() == 0


@pytest.mark.parametrize("mode", ["monitored", "live", "priming"])
def test_stop_serializes_with_every_camera_start(hdf5_camera, mode):
    """
    Stop cannot finish ahead of an in-flight camera start and leave Acquire enabled.
    """
    camera = hdf5_camera
    if mode == "monitored":
        wait(camera.stage())
        camera.hold_camera = True
        operation = camera.trigger
    elif mode == "live":
        operation = camera.start_live
    else:
        camera.hdf5.array_size.put((0, 0, 0))
        operation = camera.components.prime_hdf5
    writing, release, stopping = threading.Event(), threading.Event(), threading.Event()
    original_put, original_stop = camera.cam.acquire.put, camera.on_stop

    def hold_start(value, **kwargs):
        if value == 1:
            writing.set()
            assert release.wait(timeout=2)
        return original_put(value, **kwargs)

    def announce_stop():
        camera.stopped = True
        stopping.set()
        original_stop()

    with (
        mock.patch.object(camera.cam.acquire, "put", side_effect=hold_start),
        mock.patch.object(camera, "on_stop", side_effect=announce_stop),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        started = pool.submit(operation)
        assert writing.wait(timeout=2)
        stopped = pool.submit(camera.stop)
        assert stopping.wait(timeout=2)
        try:
            assert not stopped.done()
        finally:
            release.set()
        stopped.result(timeout=2)
        try:
            wait(started.result(timeout=2))
        except DeviceStoppedError:
            pass
    assert camera.stopped
    assert camera.cam.acquire.get() == 0
    assert [value for name, value in camera.writes if name == "acquire"][-1] == 0


def test_live_shutdown_becomes_inactive_only_after_successful_acknowledgement(camera):
    """
    A pending stop status retains live ownership until backend shutdown is acknowledged.
    """
    wait(camera.start_live())
    stopped = ad_components.StatusBase()
    with mock.patch.object(camera, "on_live_mode_stops", return_value=stopped):
        returned = camera.stop_live()
        assert camera._live_active
        assert camera.cam.acquire.get() == 1
        camera.components.stop_live()
        stopped.set_finished()
        returned.wait(timeout=1)
        assert not camera._live_active
        assert camera.cam.acquire.get() == 0


@pytest.mark.parametrize("source", list(AcquisitionSource))
@pytest.mark.parametrize("manual", [False, True])
def test_fixed_async_waits_for_configured_frames_and_does_not_stop_input(camera, source, manual):
    """
    Fixed async counts come from scan points/bursts or manual NumImages for either source.
    """
    camera.external_trigger_mode = VimbaTriggerMode.ON
    camera.acquisition_source.put(source.value)
    camera.acquisition_mode.put(AcquisitionMode.FIXED.value)
    camera.use_scan_timing.put(not manual)
    camera.cam.num_images.put(4)
    camera.hold_camera = True
    set_scan(camera, "async")
    count = 4 if manual else 6
    wait(camera.stage())
    assert camera.cam.image_mode.get() == "Multiple"
    assert camera.cam.num_images.get() == count
    assert camera.roi.stats1.ts_num_points.get() == count
    completed = camera.complete()
    assert not completed.done
    assert camera.cam.acquire.get() == 1
    camera.trigger().wait(timeout=1)  # BEC trigger must not reacquire async input.
    camera.emit_frames(count - 1)
    assert camera.cam.acquire.get() == 1
    assert not completed.done
    camera.emit_frames(1)
    completed.wait(timeout=2)
    assert camera.cam.acquire.get() == 0
    assert camera.cam.array_counter.get() == count


def test_internal_fixed_async_can_finish_before_complete_is_called(camera):
    """
    A fast internal fixed acquisition starts at stage and can already be idle at complete.
    """
    camera.acquisition_mode.put("fixed")
    set_scan(camera, "async")
    wait(camera.stage())
    ad_components.SubscriptionStatus(
        camera.cam.array_counter, lambda *, value, **_: value >= 6, run=True, timeout=2
    ).wait(timeout=2)
    ad_components.SubscriptionStatus(
        camera.cam.acquire, lambda *, value, **_: value == 0, run=True, timeout=2
    ).wait(timeout=2)
    camera.complete().wait(timeout=2)
    assert camera.cam.array_counter.get() == 6


def test_fixed_async_rejects_camera_idle_before_expected_count(camera):
    """
    Early idle is a short fixed acquisition, not successful scan completion.
    """
    camera.acquisition_mode.put("fixed")
    camera.hold_camera = True
    set_scan(camera, "async")
    wait(camera.stage())
    camera.emit_frames(2)
    camera.cam.acquire.put(0)
    with pytest.raises(RuntimeError, match="received 2 frames, expected 6"):
        camera.complete().wait(timeout=2)


@pytest.mark.parametrize("points", [0, -1, True, 2.5, None])
def test_fixed_async_requires_positive_scan_point_count(camera, points):
    """
    A fixed scan must resolve an exact positive total before camera input can start.
    """
    camera.acquisition_mode.put("fixed")
    set_scan(camera, "async")
    camera.scan_info.msg.info["num_points"] = points
    with pytest.raises(ValueError, match="positive integer"):
        wait(camera.stage())
    assert camera.cam.acquire.get() == 0


@pytest.mark.parametrize("mode", ["internal", "external", "auto", "invalid"])
def test_invalid_async_length_is_rejected(camera, mode):
    """
    Acquisition length accepts only fixed or continuous; source has its own setting.
    """
    camera.acquisition_mode.put(mode)
    set_scan(camera, "async")
    with pytest.raises(ValueError):
        wait(camera.stage())
    assert camera.cam.acquire.get() == 0


def test_fixed_async_rejects_scan_larger_than_roi_limit(camera):
    """
    A fixed frame count must fit both the requested scan limit and IOC waveform capacity.
    """
    camera.acquisition_mode.put("fixed")
    camera.async_frame_limit = 5
    set_scan(camera, "async")
    with pytest.raises(ValueError, match="exceeds async_frame_limit"):
        wait(camera.stage())
    assert camera.cam.acquire.get() == 0


def test_fixed_async_hdf5_waits_for_all_frames_even_with_delayed_camera_cache(hdf5_camera):
    """
    Fixed input and HDF5 each finish their expected count before file closure is reported.
    """
    camera = hdf5_camera
    camera.acquisition_mode.put("fixed")
    camera.hold_camera = True
    set_scan(camera, "async")
    wait(camera.stage())
    completed = camera.complete()
    camera.hdf5.num_captured.put(2)
    camera.emit_frames(6)
    assert not completed.done
    assert camera.hdf5.capture.get() == 1
    original_get = camera.cam.array_counter.get

    def delayed_camera_counter(*, use_monitor=True, **kwargs):
        return 0 if use_monitor else original_get(**kwargs)

    with mock.patch.object(camera.cam.array_counter, "get", side_effect=delayed_camera_counter):
        camera.hdf5.num_captured.put(6)
        completed.wait(timeout=2)
    assert camera.hdf5.capture.get() == 0
    assert camera.file_event.put.call_args.kwargs["successful"] is True


def test_continuous_async_hdf5_does_not_enforce_exact_frame_count(hdf5_camera):
    """
    Open-ended input stops at complete and a nonempty file need not match camera counts.
    """
    camera = hdf5_camera
    set_scan(camera, "async")
    wait(camera.stage())
    camera.emit_frames(6)
    camera.hdf5.num_captured.put(4)
    camera.complete().wait(timeout=2)
    assert camera.cam.acquire.get() == 0
    assert camera.hdf5.capture.get() == 0
    assert camera.file_event.put.call_args.kwargs["successful"] is True


def test_fixed_async_without_roi_outputs_is_not_limited_by_roi_buffer_setting(camera):
    """
    The optional ROI sample cap does not restrict a camera with no selected ROI outputs.
    """
    camera.roi.active.put(False)
    camera.async_frame_limit = 2
    camera.acquisition_mode.put("fixed")
    camera.hold_camera = True
    set_scan(camera, "async")
    wait(camera.stage())
    assert camera.cam.num_images.get() == 6
    completed = camera.complete()
    camera.emit_frames(6)
    completed.wait(timeout=2)


def test_overlapping_live_stops_share_one_acknowledgement(camera):
    """
    An older pending shutdown cannot outlive a newer stop and clear a restarted camera.
    """
    wait(camera.start_live())
    first_ack, second_ack = ad_components.StatusBase(), ad_components.StatusBase()
    original = camera.on_live_mode_stops
    with mock.patch.object(
        camera, "on_live_mode_stops", side_effect=[first_ack, second_ack]
    ) as hook:
        first = camera.stop_live()
        second = camera.stop_live()
        assert first is second
        hook.assert_called_once()
        assert camera._live_active
        original()
        first_ack.set_finished()
        first.wait(timeout=1)
        assert not camera._live_active
        wait(camera.start_live())
        assert camera._live_active
        assert camera.cam.acquire.get() == 1
        third = camera.stop_live()
        assert third is not first
        assert hook.call_count == 2
        assert not third.done
        original()
        second_ack.set_finished()
        third.wait(timeout=1)
        assert not camera._live_active
        assert camera.cam.acquire.get() == 0


def test_concurrent_live_stops_share_status_before_backend_hook_returns(camera):
    """
    Register shutdown ownership before backend I/O so simultaneous callers cannot duplicate it.
    """
    wait(camera.start_live())
    entered, release = threading.Event(), threading.Event()
    acknowledged = ad_components.StatusBase()
    original = camera.on_live_mode_stops

    def delayed_hook():
        entered.set()
        assert release.wait(timeout=2)
        return acknowledged

    with (
        mock.patch.object(camera, "on_live_mode_stops", side_effect=delayed_hook) as hook,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        first_call = pool.submit(camera.stop_live)
        assert entered.wait(timeout=2)
        try:
            second = pool.submit(camera.stop_live).result(timeout=1)
            assert not second.done
            hook.assert_called_once()
        finally:
            release.set()
        first = first_call.result(timeout=2)
        assert first is second
        original()
        acknowledged.set_finished()
        first.wait(timeout=1)
    assert not camera._live_active
    assert camera.cam.acquire.get() == 0


def test_restarted_live_does_not_reuse_a_completed_backend_shutdown(camera):
    """
    A new acquisition can be stopped even while the previous status is notifying callers.
    """
    wait(camera.start_live())
    first_ack, second_ack = ad_components.StatusBase(), ad_components.StatusBase()
    original = camera.on_live_mode_stops
    with mock.patch.object(
        camera, "on_live_mode_stops", side_effect=[first_ack, second_ack]
    ) as hook:
        first = camera.stop_live()
        finish = first.set_finished
        next_stop = []

        def restart_before_notification():
            wait(camera.start_live())
            next_stop.append(camera.stop_live())
            finish()

        original()
        with mock.patch.object(first, "set_finished", side_effect=restart_before_notification):
            first_ack.set_finished()
        first.wait(timeout=1)
        assert hook.call_count == 2
        assert next_stop[0] is not first
        assert not next_stop[0].done
        original()
        second_ack.set_finished()
        next_stop[0].wait(timeout=1)
        assert not camera._live_active
        assert camera.cam.acquire.get() == 0


@pytest.mark.parametrize("interruption", ["device_stop", "disable_live", "stage"])
def test_pending_live_restart_cannot_erase_a_later_stop(camera, interruption):
    """
    A restart waiting for prior shutdown must not rearm after a newer stop has finished.
    """
    wait(camera.start_live())
    acknowledgement = ad_components.StatusBase()
    original_stop = camera.on_live_mode_stops
    waiting, resumed, release = threading.Event(), threading.Event(), threading.Event()
    with mock.patch.object(camera, "on_live_mode_stops", return_value=acknowledgement):
        shared = camera.stop_live(update_preference=False)
        original_wait = shared.wait

        def wait_for_shutdown(*args, **kwargs):
            restarting = threading.current_thread().name.startswith("pending-restart")
            if restarting:
                waiting.set()
            original_wait(*args, **kwargs)
            if restarting:
                resumed.set()
                assert release.wait(timeout=2)

        with (
            mock.patch.object(shared, "wait", side_effect=wait_for_shutdown),
            mock.patch.object(
                camera, "on_live_mode_starts", wraps=camera.on_live_mode_starts
            ) as start_hook,
            ThreadPoolExecutor(max_workers=1, thread_name_prefix="pending-restart") as pool,
        ):
            restart = pool.submit(camera.start_live)
            assert waiting.wait(timeout=1)
            try:
                with ThreadPoolExecutor(max_workers=1) as stop_pool:
                    operation = {
                        "device_stop": camera.stop,
                        "disable_live": camera.stop_live,
                        "stage": camera.stage,
                    }[interruption]
                    stopping = stop_pool.submit(operation)
                    original_stop()
                    acknowledgement.set_finished()
                    assert resumed.wait(timeout=1)
                    wait(stopping.result(timeout=2))
                assert camera.cam.acquire.get() == 0
                release.set()
                error = RuntimeError if interruption == "stage" else DeviceStoppedError
                with pytest.raises(error):
                    restart.result(timeout=2)
                start_hook.assert_not_called()
            finally:
                release.set()
        assert camera.cam.acquire.get() == 0
        assert not camera._live_active
        if interruption == "device_stop":
            assert camera.stopped
    # A genuinely new request after stop may still start live acquisition.
    if interruption == "stage":
        wait(camera.unstage())
    wait(camera.start_live())
    assert camera.cam.acquire.get() == 1


def test_disabled_live_resume_does_not_clear_a_previous_stop(camera):
    """
    Internal resume with live disabled is a no-op, including the device's stopped state.
    """
    camera.live_enabled.put(False)
    camera.stop()
    camera.start_live(update_preference=False).wait(timeout=1)
    assert camera.stopped
    assert not camera._live_active
    assert camera.cam.acquire.get() == 0
