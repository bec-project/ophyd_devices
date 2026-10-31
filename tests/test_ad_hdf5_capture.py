"""HDF5 capture contracts exercised without a concrete camera or AD acquisition backend."""

from enum import IntEnum
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ophyd import Signal

from ophyd_devices.devices.areadetector.hdf5_capture import ADHDF5Capture
from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError
from ophyd_devices.utils.psi_device_base_utils import FileHandler, StatusBase, release_statuses


class PV(Signal):
    """Soft readback with IOC-like callbacks and an observable command log."""

    def __init__(self, name, value, writes):
        self.writes = writes
        self.on_write = None
        super().__init__(name=name, value=value)
        # Populate the initial monitor cache used by run=True subscriptions.
        Signal.put(self, value)

    def get(self, *, timeout=None, use_monitor=True, **kwargs):
        return super().get(**kwargs)

    def put(self, value, **kwargs):
        self.writes.append((self.name, value, kwargs))
        Signal.put(self, value)
        if self.on_write is not None:
            self.on_write(value)


class TriggerMode(IntEnum):
    INTERNAL = 0


class CameraStub:
    """Only the camera services and PV groups consumed by ADHDF5Capture."""

    def __init__(self, directory):
        self.name = "camera"
        self.stopped = False
        self.io_timeout = 0.1
        self.acquisition_timeout = 0.2
        self.internal_trigger_mode = TriggerMode.INTERNAL
        self._frame_origin = 0
        self.hdf5_path_mapping = None
        self.writes = []
        self.statuses = set()
        self.file_event = SimpleNamespace(put=Mock())
        self.file_utils = FileHandler()
        self._scan_message = SimpleNamespace(
            info={"file_components": [str(directory / "new_scan" / "S00001"), "h5"]},
            scan_parameters={"system_config": {}},
        )
        self.path = str(directory / "new_scan" / "S00001_camera.h5")
        self.save_frame_data = self.pv("save_frame_data", True)
        self.cam = self.group(
            "cam",
            acquire=0,
            acquire_time=12.0,
            acquire_period=13.0,
            array_callbacks=0,
            image_mode="Multiple",
            trigger_mode=3,
            array_counter=0,
        )
        self.hdf5 = self.group(
            "hdf5",
            capture=0,
            enable=0,
            file_path="",
            file_name="previous.h5",
            file_template="%s%s_%d.h5",
            file_write_mode=0,
            auto_increment=1,
            auto_save=1,
            lazy_open=0,
            num_capture=1,
            num_captured=7,
            array_size=(0, 2, 2),
            file_path_exists=1,
            write_file=0,
            write_status=0,
            write_message="",
        )
        self.hdf5.array_size.width = self.pv("hdf5_width", 2)
        self.hdf5.array_size.on_write = lambda value: self.hdf5.array_size.width.put(value[-1])
        self.hdf5.capture.on_write = lambda value: (
            self.hdf5.num_captured.put(0) if value == 1 else None
        )
        self.failure = Mock()
        self.helper = ADHDF5Capture(self, command_lock=RLock(), on_failure=self.failure)

    def pv(self, name, value):
        return PV(name, value, self.writes)

    def group(self, prefix, **values):
        return SimpleNamespace(
            **{name: self.pv(f"{prefix}_{name}", value) for name, value in values.items()}
        )

    def check_cancelled(self):
        if self.stopped:
            raise DeviceStoppedError("Camera interrupted")

    def cancel_on_stop(self, status):
        if not status.done:
            self.statuses.add(status)
            status.add_callback(lambda finished: self.statuses.discard(finished))

    def interrupt(self):
        self.stopped = True
        for status in tuple(self.statuses):
            if not status.done:
                status.set_exception(DeviceStoppedError("Camera interrupted"))


@pytest.fixture
def camera(tmp_path):
    instance = CameraStub(tmp_path)
    yield instance
    release_statuses(tuple(instance.statuses), reason="Test cleanup")
    for group in (instance.cam, instance.hdf5):
        if group is not None:
            for signal in vars(group).values():
                signal.destroy()
    instance.save_frame_data.destroy()


def finished_status():
    status = StatusBase()
    status.set_finished()
    return status


def test_absent_or_disabled_writer_does_not_acquire_or_publish(camera):
    writer = camera.hdf5
    camera.hdf5 = None
    camera.helper.prime()
    camera.helper.stage()
    acquisition = finished_status()
    assert (
        camera.helper.complete(acquisition, software_trigger=True, async_frames=None) is acquisition
    )
    camera.helper.stop()
    assert not camera.writes
    camera.hdf5 = writer
    camera.save_frame_data.put(False)
    camera.writes.clear()
    camera.helper.prime()
    camera.helper.stage()
    assert camera.cam.acquire.get() == 0
    assert writer.enable.get() == writer.auto_save.get() == writer.capture.get() == 0
    camera.file_event.put.assert_not_called()


def test_primed_writer_needs_no_preparation_commands(camera):
    camera.helper.prime()
    assert camera.writes == []
    camera.file_event.put.assert_not_called()


def test_cold_priming_is_unsaved_and_restores_controller_settings(camera):
    camera.hdf5.array_size.put((0, 0, 0))
    originals = {
        name: getattr(camera.cam, name).get()
        for name in vars(camera.cam)
        if name != "array_counter"
    }

    def acquire(value):
        if value == 1:
            assert camera.hdf5.capture.get() == camera.hdf5.auto_save.get() == 0
            assert camera.cam.acquire_time.get() == camera.cam.acquire_period.get() == 0.01
            assert camera.cam.image_mode.get() == "Single"
            camera.hdf5.array_size.put((0, 512, 512))
            camera.cam.acquire.put(0)

    camera.cam.acquire.on_write = acquire
    camera.helper.prime()
    assert {name: getattr(camera.cam, name).get() for name in originals} == originals
    assert camera.hdf5.enable.get() == 0
    assert camera.hdf5.auto_save.get() == 1
    camera.file_event.put.assert_not_called()
    assert not camera.hdf5.capture._callbacks[camera.hdf5.capture.SUB_VALUE]
    assert not camera.hdf5.num_captured._callbacks[camera.hdf5.num_captured.SUB_VALUE]
    assert not camera.cam.acquire._callbacks[camera.cam.acquire.SUB_VALUE]


@pytest.mark.parametrize("cancel", [False, True])
def test_failed_priming_restores_timing_and_releases_watchers(camera, cancel):
    camera.hdf5.array_size.put((0, 0, 0))
    original = RuntimeError("Acquisition command failed")

    def acquire(value):
        if value == 1:
            if cancel:
                camera.interrupt()
            else:
                raise original

    camera.cam.acquire.on_write = acquire
    with pytest.raises(DeviceStoppedError if cancel else RuntimeError) as caught:
        camera.helper.prime()
    if not cancel:
        assert caught.value is original
    assert camera.cam.acquire.get() == 0
    assert camera.cam.acquire_time.get() == 12.0
    assert camera.cam.acquire_period.get() == 13.0
    assert not camera.hdf5.capture._callbacks[camera.hdf5.capture.SUB_VALUE]
    assert not camera.hdf5.num_captured._callbacks[camera.hdf5.num_captured.SUB_VALUE]
    assert not camera.cam.acquire._callbacks[camera.cam.acquire.SUB_VALUE]
    camera.file_event.put.assert_not_called()


def test_stage_creates_directory_before_configuring_translated_ioc_path(camera):
    camera.hdf5_path_mapping = {str(Path(camera.path).parents[1]): "/data"}
    expected_directory = Path(camera.path).parent
    camera.hdf5.file_path.on_write = lambda _: expected_directory.is_dir() or pytest.fail(
        "Missing scan directory"
    )
    assert not expected_directory.exists()
    camera.helper.stage()
    assert camera.hdf5.file_path.get() == "/data/new_scan/"
    assert camera.hdf5.file_name.get() == Path(camera.path).name
    assert camera.hdf5.file_template.get() == "%s%s"
    assert camera.hdf5.file_write_mode.get() == 2
    assert camera.hdf5.num_capture.get() == 0
    assert camera.hdf5.capture.get() == 1
    assert camera.hdf5.num_captured.get() == 0
    assert camera.file_event.put.call_args.kwargs == {
        "file_path": camera.path,
        "done": False,
        "successful": False,
        "hinted_h5_entries": {"data": "/entry/data/data"},
    }


@pytest.mark.parametrize("unprimed", [True, False])
def test_stage_rejects_unprepared_writer_before_announcing_file(camera, unprimed):
    if unprimed:
        camera.hdf5.array_size.put((0, 0, 0))
    else:
        camera.hdf5.file_path_exists.put(0)
    with pytest.raises(RuntimeError, match="unprimed|output directory is unavailable"):
        camera.helper.stage()
    camera.file_event.put.assert_not_called()
    assert camera.cam.acquire.get() == camera.hdf5.capture.get() == 0


@pytest.mark.parametrize("failure", ["arm", "counter_reset"])
def test_stage_requires_new_capture_and_counter_reset_acknowledgements(camera, failure):
    camera.io_timeout = 0.02
    if failure == "arm":
        original_put = camera.hdf5.capture.put
        camera.hdf5.capture.put = lambda value, **kwargs: (
            original_put(value, **kwargs) if value == 0 else None
        )
    else:
        camera.hdf5.capture.on_write = None
    with pytest.raises(TimeoutError, match="acknowledged|capture counter reset"):
        camera.helper.stage()
    assert camera.hdf5.capture.get() == 0
    assert camera.file_event.put.call_args.kwargs["successful"] is False
    assert camera.file_event.put.call_args.kwargs["done"] is True
    assert not camera.hdf5.capture._callbacks[camera.hdf5.capture.SUB_VALUE]
    assert not camera.hdf5.num_captured._callbacks[camera.hdf5.num_captured.SUB_VALUE]
    assert not camera.cam.acquire._callbacks[camera.cam.acquire.SUB_VALUE]


def test_busy_capture_commands_never_request_put_completion(camera):
    capture = camera.hdf5.capture
    original_put = capture.put

    def busy_put(value, *, wait=False, use_complete=False, **kwargs):
        assert (
            not wait and not use_complete
        ), "Busy record put completion waits for the whole capture"
        return original_put(value, **kwargs)

    capture.put = busy_put
    camera.helper.stage()
    assert capture.get() == 1
    camera.helper.stop()
    assert capture.get() == 0
    assert camera.file_event.put.call_args.kwargs["successful"] is False


def test_missing_stop_acknowledgement_still_publishes_failure_and_releases_watcher(camera):
    camera.helper.stage()
    camera.io_timeout = 0.02
    capture = camera.hdf5.capture
    capture.put = lambda *args, **kwargs: None
    with pytest.raises(TimeoutError, match="capture command 0 was not acknowledged"):
        camera.helper.stop()
    assert camera.file_event.put.call_args.kwargs["done"] is True
    assert camera.file_event.put.call_args.kwargs["successful"] is False
    assert not capture._callbacks[capture.SUB_VALUE]


@pytest.mark.parametrize(
    "mapping,path,expected,error",
    [
        ({}, "/host/data/a.h5", "/host/data/a.h5", None),
        ({"/host": "/data", "/host/data": "/specific"}, "/host/data/a.h5", "/specific/a.h5", None),
        ({"/host/data": "/data"}, "/host/database/a.h5", None, ValueError),
        ({"relative": "/data"}, "/host/data/a.h5", None, ValueError),
        ({"/host/data": 1}, "/host/data/a.h5", None, TypeError),
    ],
)
def test_path_mapping_validates_prefixes_and_uses_most_specific(
    camera, mapping, path, expected, error
):
    camera.hdf5_path_mapping = mapping
    if error is None:
        assert camera.helper.ioc_path(path) == expected
    else:
        with pytest.raises(error):
            camera.helper.ioc_path(path)


def test_completion_waits_for_acquisition_then_written_frames_and_announces_once(camera):
    # Frames are driven by this test; keep the observation phase free of deadlines.
    camera.acquisition_timeout = None
    camera.helper.stage()
    acquisition = StatusBase()
    camera.cam.array_counter.put(3)
    completed = camera.helper.complete(acquisition, software_trigger=True, async_frames=None)
    assert completed is camera.helper.complete(
        acquisition, software_trigger=True, async_frames=None
    )
    camera.hdf5.num_captured.put(3)
    assert not completed.done
    camera.hdf5.num_captured.put(0)
    acquisition.set_finished()
    assert not completed.done
    camera.hdf5.num_captured.put(2)
    assert not completed.done
    camera.hdf5.num_captured.put(3)
    completed.wait(timeout=1)
    assert camera.hdf5.capture.get() == 0
    assert camera.file_event.put.call_count == 2
    assert camera.file_event.put.call_args.kwargs["successful"] is True
    camera.helper.stop()
    assert camera.file_event.put.call_count == 2
    camera.failure.assert_not_called()


@pytest.mark.parametrize("frames", [None, 5])
def test_async_completion_distinguishes_continuous_and_fixed_counts(camera, frames):
    # The explicit final wait bounds this test, rather than a background timer.
    camera.acquisition_timeout = None
    camera.helper.stage()
    camera.hdf5.num_captured.put(2)
    completed = camera.helper.complete(
        finished_status(), software_trigger=False, async_frames=frames
    )
    if frames is not None:
        assert not completed.done
        camera.hdf5.num_captured.put(frames)
    completed.wait(timeout=1)
    assert camera.file_event.put.call_args.kwargs["successful"] is True


def test_writer_error_closes_capture_and_publishes_failure_before_status_fails(camera):
    camera.helper.stage()
    camera.hdf5.num_captured.put(2)
    camera.cam.array_counter.put(2)
    camera.hdf5.write_status.put(1)
    camera.hdf5.write_message.put("Disk full")
    completed = camera.helper.complete(finished_status(), software_trigger=True, async_frames=None)
    with pytest.raises(RuntimeError, match="Disk full"):
        completed.wait(timeout=1)
    assert camera.hdf5.capture.get() == 0
    assert camera.file_event.put.call_args.kwargs["done"] is True
    assert camera.file_event.put.call_args.kwargs["successful"] is False
    camera.failure.assert_called_once()


def test_interruption_cancels_pending_completion_and_publishes_failed_file(camera):
    # Cancellation must finish the pending phase, even when the observer is delayed.
    camera.acquisition_timeout = None
    camera.helper.stage()
    camera.cam.array_counter.put(3)
    completed = camera.helper.complete(finished_status(), software_trigger=True, async_frames=None)
    assert not completed.done
    camera.interrupt()
    with pytest.raises(DeviceStoppedError):
        completed.wait(timeout=1)
    assert camera.hdf5.capture.get() == 0
    assert camera.file_event.put.call_args.kwargs["successful"] is False
    assert not camera.hdf5.capture._callbacks[camera.hdf5.capture.SUB_VALUE]
    assert not camera.hdf5.num_captured._callbacks[camera.hdf5.num_captured.SUB_VALUE]
    assert not camera.cam.acquire._callbacks[camera.cam.acquire.SUB_VALUE]
