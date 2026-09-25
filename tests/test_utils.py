import threading
import time
from functools import partial
from unittest import mock

import numpy as np
import ophyd
import pytest
from bec_lib import messages
from bec_lib.bec_errors import ExceptionWithErrorInfo
from ophyd import Component as Cpt
from ophyd import Device, EpicsSignalRO, Signal
from ophyd.status import DeviceStatus as OphydDeviceStatus
from ophyd.status import MoveStatus as OphydMoveStatus
from ophyd.status import Status as OphydStatus
from ophyd.status import StatusBase as OphydStatusBase
from ophyd.status import WaitTimeoutError
from typeguard import TypeCheckError

from ophyd_devices.devices.psi_motor import EpicsMotor
from ophyd_devices.tests.utils import MockPV, patched_device
from ophyd_devices.utils.bec_signals import (
    AsyncMultiSignal,
    AsyncSignal,
    BECMessageSignal,
    DynamicSignal,
    FileEventSignal,
    PreviewSignal,
    ProgressSignal,
)
from ophyd_devices.utils.psi_device_base_utils import (
    AndStatus,
    CompareStatus,
    DeviceStatus,
    ExceptionStatus,
    FileHandler,
    MoveStatus,
    Status,
    StatusBase,
    StatusTimeoutErrorWithErrorInfo,
    SubscriptionStatus,
    TaskHandler,
    TaskKilledError,
    TaskState,
    TaskStatus,
    TransitionStatus,
)
from ophyd_devices.utils.signal_monitoring import SignalMonitoring

# pylint: disable=protected-access
# pylint: disable=redefined-outer-name

##########################################
#########  Test Task Handler  ############
##########################################


@pytest.fixture(scope="function")
def mock_epics_signal_ro():
    name = "epics_signal_ro"
    read_pv = "TEST:EPICS_SIGNAL_RO"
    with mock.patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        dev = EpicsSignalRO(name=name, read_pv=read_pv)
        yield dev


@pytest.fixture
def file_handler():
    """Fixture for FileHandler"""
    yield FileHandler()


@pytest.fixture
def device():
    """Fixture for Device"""
    yield Device(name="device")


@pytest.fixture
def task_handler(device):
    """Fixture for TaskHandler"""
    yield TaskHandler(parent=device)


def test_utils_file_handler_has_full_path(file_handler):
    """Ensure that file_handler has a get_full_path method"""
    assert hasattr(file_handler, "get_full_path")


def test_utils_task_status(device):
    """Test TaskStatus creation"""
    status = TaskStatus(device)
    assert status.obj.name == "device"
    assert status.state == "not_started"
    assert status.task_id == status._task_id
    status.state = "running"
    assert status.state == TaskState.RUNNING
    status.state = TaskState.COMPLETED
    assert status.state == "completed"


def test_utils_task_handler_submit_task_with_args(task_handler):
    """Ensure that task_handler has a submit_task method"""

    def my_task(input_arg: bool, input_kwarg: bool = False):
        if input_kwarg is True:
            raise ValueError("input_kwarg is True")
        if input_arg is True:
            return True
        return False

    # This should fail
    with pytest.raises(TypeError):
        status = task_handler.submit_task(my_task)
        status.wait()
    # This should pass

    task_stopped = threading.Event()

    def finished_cb():
        task_stopped.set()

    status = task_handler.submit_task(
        my_task, task_args=(True,), task_kwargs={"input_kwarg": False}
    )
    status.add_callback(finished_cb)
    task_stopped.wait()
    assert status.done is True
    assert status.state == TaskState.COMPLETED
    # This should fail
    task_stopped = threading.Event()
    status = task_handler.submit_task(my_task, task_args=(True,), task_kwargs={"input_kwarg": True})
    with pytest.raises(ValueError):
        status.wait()
    assert status.state == TaskState.ERROR
    assert status.done is True
    assert status.exception().__class__ == ValueError


@pytest.mark.timeout(100)
def test_utils_task_handler_task_killed(task_handler):
    """Ensure that task_handler has a submit_task method"""
    # No tasks should be running
    assert len(task_handler._tasks) == 0
    event = threading.Event()
    task_stopped = threading.Event()
    task_started = threading.Event()

    def finished_cb():
        task_stopped.set()

    def my_wait_task():
        task_started.set()
        for _ in range(100):
            event.wait(timeout=0.1)

    # Create task
    status = task_handler.submit_task(my_wait_task, run=False)
    status.add_callback(finished_cb)
    assert status.state == TaskState.NOT_STARTED
    # Start task
    task_handler.start_task(status)
    task_started.wait()
    assert status.state == TaskState.RUNNING
    # Stop task
    task_handler.kill_task(status)
    task_stopped.wait()
    assert status.state == TaskState.KILLED
    assert status.exception().__class__ == TaskKilledError


@pytest.mark.timeout(100)
def test_utils_task_handler_task_successful(task_handler):
    """Ensure that the task handler runs a successful task"""
    assert len(task_handler._tasks) == 0
    event = threading.Event()
    task_stopped = threading.Event()
    task_started = threading.Event()

    def finished_cb():
        task_stopped.set()

    def my_wait_task():
        task_started.set()
        for _ in range(100):
            ret = event.wait(timeout=0.1)
            if ret is True:
                break

    status = task_handler.submit_task(my_wait_task, run=False)
    status.add_callback(finished_cb)
    task_handler.start_task(status)
    task_started.wait()
    assert status.state == TaskState.RUNNING
    event.set()
    task_stopped.wait()
    assert status.state == TaskState.COMPLETED


def test_utils_task_handler_shutdown(task_handler):
    """Test to shutdown the handler"""

    task_completed_cb1 = threading.Event()
    task_completed_cb2 = threading.Event()

    def finished_cb1():
        task_completed_cb1.set()

    def finished_cb2():
        task_completed_cb2.set()

    def cb1():
        for _ in range(1000):
            time.sleep(0.2)

    def cb2():
        for _ in range(1000):
            time.sleep(0.2)

    status1 = task_handler.submit_task(cb1)
    status1.add_callback(finished_cb1)
    status2 = task_handler.submit_task(cb2)
    status2.add_callback(finished_cb2)
    assert len(task_handler._tasks) == 2
    assert status1.state == TaskState.RUNNING
    assert status2.state == TaskState.RUNNING
    task_handler.shutdown()
    task_completed_cb1.wait()
    task_completed_cb2.wait()
    assert len(task_handler._tasks) == 0
    assert status1.state == TaskState.KILLED
    assert status2.state == TaskState.KILLED
    assert status1.exception().__class__ == TaskKilledError


@pytest.mark.timeout(10)
def test_utils_signal_monitoring_of_script():
    """Verify polling triggers repeatedly and approximately at the configured cadence."""
    monitoring = SignalMonitoring(name="test_signal_monitoring")
    monitoring.polling_interval = 0.05

    callback_timestamps = []
    reached_target_calls = threading.Event()

    def monitored_callback():
        callback_timestamps.append(time.perf_counter())
        if len(callback_timestamps) >= 6:
            reached_target_calls.set()

    callback_id = monitoring.register_signal(monitored_callback)

    try:
        monitoring.start()
        assert reached_target_calls.wait(
            timeout=1.5
        ), "SignalMonitoring did not poll the registered callback enough times in time."
        monitoring.stop()

        # Use a subset of intervals to reduce startup/shutdown jitter influence.
        intervals = [
            callback_timestamps[idx + 1] - callback_timestamps[idx]
            for idx in range(len(callback_timestamps) - 1)
        ]
        stable_intervals = intervals[1:-1] if len(intervals) > 4 else intervals

        assert len(callback_timestamps) >= 6
        assert stable_intervals

        mean_interval = float(np.mean(stable_intervals))
        assert mean_interval == pytest.approx(monitoring.polling_interval, abs=0.03)

        # Guard against pathological bursts or stalls.
        assert min(stable_intervals) > 0.02
        assert max(stable_intervals) < 0.15
    finally:
        monitoring.remove_signal(callback_id)
        monitoring.shutdown()


def test_utils_signal_monitoring_of_ophyd_signal():
    """Test that SignalMonitoring can monitor an ophyd Signal and trigger callbacks on value changes."""

    class MockSignalWithCounter(Signal):

        _target_event = threading.Event()
        _get_counter = 0

        def get(self):
            self._get_counter += 1
            if self._get_counter == 20:  # After 20 polls, trigger the event to stop the test
                self._target_event.set()
            return self._readback

    monitoring = SignalMonitoring(name="test_signal_monitoring")
    monitoring.polling_interval = 0.05  # 20 times per second

    signal = MockSignalWithCounter(name="test_signal", value=0)
    assert signal._get_counter == 0
    assert signal._target_event.is_set() is False

    monitoring.register_signal(signal=signal)
    monitoring.start()
    assert signal._target_event.wait(
        timeout=1.5
    ), "SignalMonitoring did not poll the Signal enough times in time."
    monitoring.stop()
    signal_counter = signal._get_counter
    assert signal_counter >= 20, f"Expected at least 20 polls, got {signal_counter}"
    time.sleep(0.2)  # Wait to ensure no more polls happen after stopping
    assert np.isclose(
        signal._get_counter, signal_counter, atol=1
    ), (  # Allow for 1 additional poll due to timing uncertainty
        "SignalMonitoring continued polling after stopping"
    )

    monitoring.shutdown()
    timer = time.time()
    while monitoring._poll_thread.is_alive():
        time.sleep(0.1)
        if time.time() - timer > 2:
            raise TimeoutError("Polling thread did not shut down within expected time.")


##########################################
#########  Test PSI cusomt signals  ######
##########################################


def test_utils_bec_message_signal():
    """Test BECMessageSignal"""
    dev = Device(name="device")
    signal = BECMessageSignal(
        name="bec_message_signal",
        bec_message_type=messages.GUIInstructionMessage,
        value=None,
        parent=dev,
    )
    assert signal.parent == dev
    assert signal._bec_message_type == messages.GUIInstructionMessage
    assert signal._readback is None
    assert signal.name == "bec_message_signal"
    assert signal.describe() == {
        "bec_message_signal": {
            "source": "BECMessageSignal:bec_message_signal",
            "dtype": "GUIInstructionMessage",
            "shape": [],
            "signal_info": {
                "data_type": "raw",
                "saved": True,
                "ndim": 0,
                "scope": "scan",
                "role": "main",
                "enabled": True,
                "rpc_access": False,
                "signals": [("bec_message_signal", 5)],
                "signal_metadata": {},
                "acquisition_group": None,
            },
        }
    }
    # Put works with Message
    msg = messages.GUIInstructionMessage(action="image", parameter={"gui_id": "test"})
    signal.put(msg)
    reading = signal.read()
    assert reading[signal.name]["value"] == msg
    # set works with dict, should call put
    msg_dict = {"action": "image", "parameter": {"gui_id": "test"}}
    status = signal.set(msg_dict)
    assert status.done is True
    reading = signal.read()
    assert reading[signal.name]["value"] == msg
    # Put fails with wrong type
    with pytest.raises(ValueError):
        signal.put("wrong_type")
    # Put fails with wrong dict
    with pytest.raises(ValueError):
        signal.put({"wrong_key": "wrong_value"})


@pytest.mark.parametrize(
    "input_msg, output_msg",
    [
        (
            messages.DeviceMessage(
                signals={"sig1": {"value": 1}, "sig2": {"value": 2}}, metadata={"info": "test"}
            ),
            messages.DeviceMessage(
                signals={"device_data_sig1": {"value": 1}, "device_data_sig2": {"value": 2}},
                metadata={"info": "test"},
            ),
        ),
        (
            messages.DeviceMessage(
                signals={"device_data_sig1": {"value": 1}, "device_data_sig2": {"value": 2}},
                metadata={"info": "test"},
            ),
            messages.DeviceMessage(
                signals={"device_data_sig1": {"value": 1}, "device_data_sig2": {"value": 2}},
                metadata={"info": "test"},
            ),
        ),
    ],
)
def test_utils_signal_normalization(input_msg, output_msg):
    """Test signal normalization utility in BECMessageSignal"""

    class DeviceWithSignal(Device):
        data = Cpt(AsyncMultiSignal, name="data", signals=["sig1", "sig2"], ndim=0, max_size=1000)

    dev = DeviceWithSignal(name="device")
    dev.data._normalize_signals(input_msg)
    assert input_msg == output_msg


def test_utils_dynamic_signal():
    """Test DynamicSignal"""
    dev = Device(name="device")
    signal = DynamicSignal(
        name="dynamic_signal", signals=["sig1", "sig2"], value=None, max_size=10, parent=dev
    )
    assert signal.parent == dev
    assert signal._bec_message_type == messages.DeviceMessage
    assert signal._readback is None
    assert signal.name == "dynamic_signal"
    assert signal.signals == [("sig1", 1), ("sig2", 1)]
    assert signal.describe() == {
        "dynamic_signal": {
            "source": "BECMessageSignal:dynamic_signal",
            "dtype": "DeviceMessage",
            "shape": [],
            "signal_info": {
                "data_type": "raw",
                "saved": True,
                "ndim": 1,
                "scope": "scan",
                "role": "main",
                "enabled": True,
                "rpc_access": False,
                "signals": [("sig1", 1), ("sig2", 1)],
                "signal_metadata": {"max_size": 10},
                "acquisition_group": None,
            },
        }
    }

    # Put works with Message
    msg_dict = {"dynamic_signal_sig1": {"value": 1}, "dynamic_signal_sig2": {"value": 2}}
    with pytest.raises(ValueError):
        # Missing metadata
        signal.put(messages.DeviceMessage(signals=msg_dict))
    metadata = {"async_update": {"type": "add", "max_shape": [None, 1000]}}
    msg = messages.DeviceMessage(signals=msg_dict, metadata=metadata)
    signal.put(msg)
    reading = signal.read()
    assert reading[signal.name]["value"] == msg
    # Set works with dict
    status = signal.set(msg_dict, metadata=metadata)
    assert status.done is True
    reading = signal.read()
    assert reading[signal.name]["value"] == msg
    # Put fails with wrong type
    with pytest.raises(TypeCheckError):
        signal.put("wrong_type")
    # Put fails with wrong dict
    with pytest.raises(TypeCheckError):
        signal.put({"wrong_key": "wrong_value"})

    # Set with acquisition group
    signal.put(msg, acquisition_group="fly-scan")
    reading = signal.read()
    msg.metadata["acquisition_group"] = "fly-scan"
    assert reading[signal.name]["value"] == msg


def test_utils_dynamic_signal_with_defaults():
    """
    Test DynamicSignal with async_update and acquisition group defaults. If only
    one sub-signal is provided for the dynamic signal, the name of the sub-signal
    will be used in the signals dict and a warning will be issued that the sub-signal
    name is being ignored.
    """
    dev = Device(name="device")
    create_signal = partial(
        DynamicSignal,
        name="dynamic_signal",
        parent=dev,
        ndim=1,
        value=None,
        max_size=10,
        async_update={"type": "add", "max_shape": [None, 1000]},
        acquisition_group="fly-scanning",
    )
    signal = create_signal(signals=["sig1", "sig2"])
    val = np.random.random(1000)
    msg_dict = {"dynamic_signal_sig1": {"value": val}}
    signal.put(msg_dict)
    reading = signal.read()
    reading_value = reading[signal.name]["value"].model_dump(exclude={"timestamp"})
    assert reading_value["signals"] == msg_dict
    assert reading_value["metadata"]["async_update"] == {"type": "add", "max_shape": [None, 1000]}
    assert reading_value["metadata"]["acquisition_group"] == "fly-scanning"

    signal.put(msg_dict, acquisition_group="different-group")
    reading = signal.read()
    assert reading[signal.name]["value"].metadata["acquisition_group"] == "different-group"

    # Test init variations for single signal
    for signal in [["sig1"], "sig1", None]:
        signal = create_signal(signals=signal)
        assert signal.signals == [(signal.name, ophyd.Kind.hinted.value)]


def test_utils_async_multi_signal():
    """Test AsyncMultiSignal, which is a DynamicSignal with strict signal validation."""
    device = Device(name="device")
    signal = AsyncMultiSignal(
        name="async_multi_signal",
        ndim=1,
        max_size=1000,
        signals=["sig1", "sig2"],
        async_update={"type": "add", "max_shape": [None, 1000]},
        parent=device,
    )
    val = np.random.random(1000)
    msg_dict = {"async_multi_signal_sig1": {"value": val}}
    with pytest.raises(ValueError):
        # Missing signal
        signal.put(msg_dict)
    msg_dict = {
        "async_multi_signal_sig1": {"value": val},
        "async_multi_signal_sig2": {"value": val},
    }
    signal.put(msg_dict)
    reading = signal.read()
    reading_value = reading[signal.name]["value"].model_dump(exclude={"timestamp"})
    assert reading_value["signals"] == msg_dict
    assert reading_value["metadata"]["async_update"] == {"type": "add", "max_shape": [None, 1000]}


def test_utils_async_signal():
    device = Device(name="device")
    signal = AsyncSignal(
        name="async_signal",
        ndim=1,
        max_size=1000,
        async_update={"type": "add", "max_shape": [None, 200]},
        parent=device,
    )
    val = np.random.random(1000)
    signal.put(
        val,
        async_update={"type": "add_slice", "max_shape": [None, 1000], "index": 1},
        acquisition_group="scan",
    )
    reading = signal.read()
    reading_value = reading[signal.name]["value"].model_dump(exclude={"timestamp"})
    assert np.array_equal(reading_value["signals"][signal.name]["value"], val)
    assert reading_value["metadata"]["async_update"] == {
        "type": "add_slice",
        "max_shape": [None, 1000],
        "index": 1,
    }
    assert reading_value["metadata"]["acquisition_group"] == "scan"


def test_utils_file_event_signal():
    """Test FileEventSignal"""
    dev = Device(name="device")
    signal = FileEventSignal(name="file_event_signal", value=None, parent=dev)
    assert signal.parent == dev
    assert signal._bec_message_type == messages.FileMessage
    assert signal._readback is None
    assert signal.name == "file_event_signal"
    assert signal.describe() == {
        "file_event_signal": {
            "source": "BECMessageSignal:file_event_signal",
            "dtype": "FileMessage",
            "shape": [],
            "signal_info": {
                "data_type": "raw",
                "saved": False,
                "ndim": 0,
                "scope": "scan",
                "role": "file_event",
                "enabled": True,
                "rpc_access": False,
                "signals": [("file_event_signal", 5)],
                "signal_metadata": {},
                "acquisition_group": None,
            },
        }
    }

    # Test put works with FileMessage
    msg_dict = {"file_path": "/path/to/another/file.txt", "done": False, "successful": True}
    msg = messages.FileMessage(**msg_dict)
    signal.put(msg)
    reading = signal.read()
    assert reading[signal.name]["value"] == msg
    # Test put works with dict
    signal.put(msg_dict)
    reading = signal.read()
    assert reading[signal.name]["value"] == msg
    # Test set with kwargs, should call put
    status = signal.set(file_path="/path/to/another/file.txt", done=False, successful=True)
    assert status.done is True
    reading = signal.read()
    assert reading[signal.name]["value"] == msg
    # Test put fails with wrong type
    with pytest.raises(ValueError):
        signal.put(1)
    # Test put fails with wrong dict
    with pytest.raises(ValueError):
        signal.put({"wrong_key": "wrong_value"})


def test_utils_preview_1d_signal():
    """Test Preview1DSignal"""
    dev = Device(name="device")
    signal = PreviewSignal(name="preview_1d_signal", ndim=1, value=None, parent=dev)
    assert signal.ndim == 1
    assert signal.parent == dev
    assert signal._bec_message_type == messages.DevicePreviewMessage
    assert signal._readback is None
    assert signal.name == "preview_1d_signal"
    assert signal.describe() == {
        "preview_1d_signal": {
            "source": "BECMessageSignal:preview_1d_signal",
            "dtype": "DevicePreviewMessage",
            "shape": [],
            "signal_info": {
                "data_type": "raw",
                "saved": False,
                "ndim": 1,
                "scope": "scan",
                "role": "preview",
                "enabled": True,
                "rpc_access": False,
                "signals": [("preview_1d_signal", 5)],
                "signal_metadata": {"num_rotation_90": 0, "transpose": False},
                "acquisition_group": None,
            },
        }
    }
    # Put works with Message
    msg_dict = {"device": dev.name, "data": np.array([1, 2, 3]), "signal": "preview_1d_signal"}
    msg = messages.DevicePreviewMessage(**msg_dict)
    signal.put(msg)
    reading = signal.read()
    assert reading[signal.name]["value"].model_dump(exclude="timestamp") == msg.model_dump(
        exclude="timestamp"
    )
    # Put works with dict
    signal.put(msg_dict)
    reading = signal.read()
    assert reading[signal.name]["value"].model_dump(exclude="timestamp") == msg.model_dump(
        exclude="timestamp"
    )
    # Put works with value
    status = signal.set(msg_dict["data"])
    assert status.done is True
    reading = signal.read()
    assert reading[signal.name]["value"].model_dump(exclude="timestamp") == msg.model_dump(
        exclude="timestamp"
    )
    # Put works with value
    signal.put(msg_dict["data"])
    reading = signal.read()
    assert reading[signal.name]["value"].model_dump(exclude="timestamp") == msg.model_dump(
        exclude="timestamp"
    )
    # Put fails with wrong type
    with pytest.raises(ValueError):
        signal.put(1)
    # Put fails with wrong dict
    with pytest.raises(ValueError):
        signal.put({"wrong_key": "wrong_value"})


def test_utils_preview_2d_signal():
    """Test Preview2DSignal"""
    dev = Device(name="device")
    signal = PreviewSignal(name="preview_2d_signal", ndim=2, value=None, parent=dev)
    assert signal.ndim == 2
    assert signal.parent == dev
    assert signal._bec_message_type == messages.DevicePreviewMessage
    assert signal._readback is None
    assert signal.name == "preview_2d_signal"
    assert signal.describe() == {
        "preview_2d_signal": {
            "source": "BECMessageSignal:preview_2d_signal",
            "dtype": "DevicePreviewMessage",
            "shape": [],
            "signal_info": {
                "data_type": "raw",
                "saved": False,
                "ndim": 2,
                "scope": "scan",
                "role": "preview",
                "enabled": True,
                "rpc_access": False,
                "signals": [("preview_2d_signal", 5)],
                "signal_metadata": {"num_rotation_90": 0, "transpose": False},
                "acquisition_group": None,
            },
        }
    }
    # Put works with Message
    msg_dict = {
        "device": dev.name,
        "data": np.array([[1, 2, 3], [4, 5, 6]]),
        "signal": "preview_2d_signal",
    }
    msg = messages.DevicePreviewMessage(**msg_dict)
    signal.put(msg)
    reading = signal.read()
    assert reading[signal.name]["value"].model_dump(exclude="timestamp") == msg.model_dump(
        exclude="timestamp"
    )
    # Put works with dict
    signal.put(msg_dict)
    reading = signal.read()
    assert reading[signal.name]["value"].model_dump(exclude="timestamp") == msg.model_dump(
        exclude="timestamp"
    )
    # Put works with value
    status = signal.set(msg_dict["data"])
    assert status.done is True
    reading = signal.read()
    assert reading[signal.name]["value"].model_dump(exclude="timestamp") == msg.model_dump(
        exclude="timestamp"
    )
    # Put works with value
    signal.put(msg_dict["data"])
    reading = signal.read()
    assert reading[signal.name]["value"].model_dump(exclude="timestamp") == msg.model_dump(
        exclude="timestamp"
    )
    # Put fails with wrong type
    with pytest.raises(ValueError):
        signal.put(1)
    # Put fails with wrong dict
    with pytest.raises(ValueError):
        signal.put({"wrong_key": "wrong_value"})


def test_utils_preview_2d_signal_transpose_rgb_swaps_only_spatial_axes():
    """Transpose must preserve channel axis for RGB-like preview data."""
    dev = Device(name="device")
    signal = PreviewSignal(
        name="preview_rgb_signal", ndim=2, value=None, parent=dev, transpose=True
    )
    data = np.arange(2 * 3 * 4).reshape(2, 3, 4)

    signal.put(data)
    reading = signal.read()[signal.name]["value"]

    np.testing.assert_array_equal(reading.data, np.swapaxes(data, 0, 1))
    assert reading.data.shape == (3, 2, 4)


def test_utils_preview_2d_signal_rotation_and_transpose_rgb():
    """Rotation and transpose should both operate on spatial axes only."""
    dev = Device(name="device")
    signal = PreviewSignal(
        name="preview_rgb_rot_signal",
        ndim=2,
        value=None,
        parent=dev,
        num_rotation_90=1,
        transpose=True,
    )
    data = np.arange(2 * 3 * 4).reshape(2, 3, 4)

    signal.put(data)
    reading = signal.read()[signal.name]["value"]

    expected = np.swapaxes(np.rot90(data, k=1, axes=(0, 1)), 0, 1)
    np.testing.assert_array_equal(reading.data, expected)


def test_utils_progress_signal():
    """Test ProgressSignal"""
    dev = Device(name="device")
    signal = ProgressSignal(name="progress_signal", value=None, parent=dev)
    assert signal.parent == dev
    assert signal._bec_message_type == messages.ProgressMessage
    assert signal._readback is None
    assert signal.name == "progress_signal"
    assert signal.describe() == {
        "progress_signal": {
            "source": "BECMessageSignal:progress_signal",
            "dtype": "ProgressMessage",
            "shape": [],
            "signal_info": {
                "data_type": "raw",
                "saved": False,
                "ndim": 0,
                "scope": "scan",
                "role": "progress",
                "enabled": True,
                "rpc_access": False,
                "signals": [("progress_signal", 5)],
                "signal_metadata": {},
                "acquisition_group": None,
            },
        }
    }
    # Put works with Message
    msg = messages.ProgressMessage(value=1, max_value=10, done=False)
    signal.put(msg)
    reading = signal.read()
    assert reading[signal.name]["value"] == msg
    # Put works with dict
    msg_dict = {"value": 1, "max_value": 10, "done": False}
    signal.put(msg_dict)
    reading = signal.read()
    assert reading[signal.name]["value"] == msg
    # Works with kwargs
    status = signal.set(value=1, max_value=10, done=False)
    assert status.done is True
    reading = signal.read()
    assert reading[signal.name]["value"] == msg
    # Put fails with wrong type
    with pytest.raises(ValueError):
        signal.put(1)
    # Put fails with wrong dict
    with pytest.raises(ValueError):
        signal.put({"wrong_key": "wrong_value"})


def test_utils_compare_status_number():
    """Test CompareStatus with different operations."""
    sig = Signal(name="test_signal", value=0)
    status = CompareStatus(signal=sig, value=5, operation_success="==")
    assert status.done is False
    sig.put(1)
    assert status.done is False
    sig.put(5)
    status.wait(timeout=5)
    assert status.done is True

    sig.put(5)
    # Test with different operations
    status = CompareStatus(signal=sig, value=5, operation_success="!=")
    assert status.done is False
    sig.put(5)
    assert status.done is False
    sig.put(6)
    assert status.done is True
    assert status.success is True
    assert status.exception() is None

    sig.put(0)
    status = CompareStatus(signal=sig, value=5, operation_success=">")
    assert status.done is False
    sig.put(5)
    assert status.done is False
    sig.put(10)
    assert status.done is True
    assert status.success is True
    assert status.exception() is None

    # Should raise
    sig.put(0)
    status = CompareStatus(signal=sig, value=5, operation_success="==", failure_value=[10])
    with pytest.raises(ValueError):
        sig.put(10)
        status.wait()
    assert status.done is True
    assert status.success is False
    assert isinstance(status.exception(), ValueError)

    # failure_operation
    sig.put(0)
    status = CompareStatus(
        signal=sig, value=5, operation_success="==", failure_value=10, operation_failure=">"
    )
    sig.put(10)
    assert status.done is False
    assert status.success is False
    sig.put(11)
    with pytest.raises(ValueError):
        status.wait()
    assert status.done is True
    assert status.success is False

    # raise if array is returned
    sig.put(0)
    status = CompareStatus(signal=sig, value=5, operation_success="==")
    with pytest.raises(ValueError):
        sig.put([1, 2, 3])
        status.wait(timeout=2)
    assert status.done is True
    assert status.success is False


def test_compare_status_string():
    """Test CompareStatus with string values"""
    sig = Signal(name="test_signal", value="test")
    status = CompareStatus(signal=sig, value="test", operation_success="==")
    assert status.done is False
    sig.put("test1")
    assert status.done is False
    sig.put("test")
    assert status.done is True

    sig.put("test")
    # Test with different operations
    status = CompareStatus(signal=sig, value="test", operation_success="!=")
    assert status.done is False
    sig.put("test")
    assert status.done is False
    sig.put("test1")
    assert status.done is True
    assert status.success is True
    assert status.exception() is None


def test_exception_status_andstatus_does_not_block_success():
    """ExceptionStatus should fail composites early but not block success while pending."""
    sig_primary_a = Signal(name="primary_a", value=0)
    sig_primary_b = Signal(name="primary_b", value=0)
    sig_watch = Signal(name="watch", value=0)

    primary_a = CompareStatus(signal=sig_primary_a, value=1, operation_success="==")
    primary_b = CompareStatus(signal=sig_primary_b, value=2, operation_success="==")
    watch = ExceptionStatus(signal=sig_watch, value=0, operation="!=")

    combined = primary_a & primary_b & watch
    sig_primary_a.put(1)
    assert not combined.done
    sig_primary_b.put(2)
    combined.wait(timeout=1)
    assert combined.done is True
    assert combined.success is True
    assert watch.done is False


def test_exception_status_andstatus_fails_early():
    """ExceptionStatus should abort a composite status when the watched value is reached."""
    sig_primary = Signal(name="primary", value=0)
    sig_watch = Signal(name="watch", value=0)

    primary = CompareStatus(signal=sig_primary, value=1, operation_success="==")
    watch = ExceptionStatus(signal=sig_watch, value=0, operation="!=")
    combined = primary & watch

    sig_watch.put(1)
    with pytest.raises(ValueError):
        combined.wait(timeout=1)
    assert combined.done is True
    assert combined.success is False


def test_exception_status_andstatus_fails_early_with_custom_exception():
    """ExceptionStatus should abort a composite status with the specified exception when the watched value is reached."""
    sig_primary = Signal(name="primary", value=0)
    sig_watch = Signal(name="watch", value=0)

    primary = CompareStatus(signal=sig_primary, value=1, operation_success="==")
    watch = ExceptionStatus(
        signal=sig_watch,
        value=0,
        operation="!=",
        exception=RuntimeError("Watch signal reached failure value"),
    )
    combined = primary & watch

    sig_watch.put(1)
    with pytest.raises(RuntimeError, match="Watch signal reached failure value"):
        combined.wait(timeout=1)
    assert combined.done is True
    assert combined.success is False


def test_exception_status_with_exception():
    """Test that ExceptionStatus raises the specified exception when the condition is met."""
    sig = Signal(name="test_signal", value=0)
    sig.put(1)
    status = ExceptionStatus(
        signal=sig, value=1, operation="==", exception=RuntimeError("Test signal reached 1")
    )
    assert status.done is True
    assert status.success is False
    with pytest.raises(RuntimeError, match="Test signal reached 1"):
        status.wait(timeout=1)


def test_transition_status():
    """Test TransitionStatus"""
    sig = Signal(name="test_signal", value=0)

    # Test strict=True, without intermediate transitions
    sig.put(0)
    status = TransitionStatus(signal=sig, transitions=[1, 2, 3], strict=True)

    assert status.done is False
    sig.put(1)
    assert status.done is False
    sig.put(2)
    assert status.done is False
    sig.put(3)
    assert status.done is True
    assert status.success is True
    assert status.exception() is None

    # Test strict=True, failure_states
    sig.put(1)
    status = TransitionStatus(signal=sig, transitions=[1, 2, 3], strict=True, failure_states=[4])
    assert status.done is False
    sig.put(4)
    with pytest.raises(ValueError):
        status.wait()

    assert status.done is True
    assert status.success is False
    assert isinstance(status.exception(), ValueError)

    # Test strict=False, with intermediate transitions
    sig.put(0)
    status = TransitionStatus(signal=sig, transitions=[1, 2, 3], strict=False)

    assert status.done is False
    sig.put(1)  # entering first transition
    sig.put(3)
    sig.put(2)  # transision
    assert status.done is False
    sig.put(4)
    sig.put(2)
    sig.put(3)  # last transition
    assert status.done is True
    assert status.success is True
    assert status.exception() is None


def test_transition_status_strings():
    """Test TransitionStatus with string values"""
    sig = Signal(name="test_signal", value="a")

    # Test strict=True, without intermediate transitions
    sig.put("a")
    status = TransitionStatus(signal=sig, transitions=["b", "c", "d"], strict=True)

    assert status.done is False
    sig.put("b")
    assert status.done is False
    sig.put("c")
    assert status.done is False
    sig.put("d")
    assert status.done is True
    assert status.success is True
    assert status.exception() is None

    # Test strict=True with additional intermediate transition

    sig.put("a")
    status = TransitionStatus(signal=sig, transitions=["b", "c", "d"], strict=True)

    assert status.done is False
    sig.put("b")  # first transition
    sig.put("e")
    sig.put("b")
    sig.put("c")  # transision
    assert status.done is False
    sig.put("f")
    sig.put("b")
    sig.put("c")
    sig.put("d")  # transision
    assert status.done is True
    assert status.success is True
    assert status.exception() is None

    # Test strict=False, with intermediate transitions
    sig.put("a")
    status = TransitionStatus(signal=sig, transitions=["b", "c", "d"], strict=False)

    assert status.done is False
    sig.put("b")  # entering first transition
    sig.put("d")
    sig.put("c")  # transision
    assert status.done is False
    sig.put("e")
    sig.put("c")
    sig.put("d")  # last transition
    assert status.done is True
    assert status.success is True


def test_compare_status_with_mock_pv(mock_epics_signal_ro):
    """Test CompareStatus with EpicsSignalRO, this tests callbacks on EpicsSignals"""

    signal = mock_epics_signal_ro
    status = CompareStatus(signal=signal, value=5, operation_success="==")
    assert status.done is False
    signal._read_pv.mock_data = 1
    assert status.done is False
    signal._read_pv.mock_data = 5
    status.wait(timeout=1)
    assert status.done is True
    assert status.success is True


def test_compare_status_raises_on_failed_comparison(mock_epics_signal_ro):
    """Test CompareStatus raises on failed comparison with EpicsSignalRO"""

    signal = mock_epics_signal_ro
    status = CompareStatus(
        signal=signal, value=5, operation_success="==", failure_value=[np.array([10])]
    )
    assert status.done is False
    signal._read_pv.mock_data = 1
    with pytest.raises(Exception):
        status.wait(timeout=5)


@pytest.mark.parametrize(
    "transitions, expected_done, expected_success",
    [
        ([1, 2, 3], True, True),  # Transitions completed successfully
        ([1, 3, 2], False, False),  # Transitions completed with an error
        ([5, 4, 2, 1, 2, 3], True, True),  # Transitions completed successfully
    ],
)
def test_transition_status_with_mock_pv(
    mock_epics_signal_ro, transitions, expected_done, expected_success
):
    """Test TransitionStatus with EpicsSignalRO, this tests callbacks on EpicsSignals"""
    # Starts immediately with 1
    signal = mock_epics_signal_ro
    signal._read_pv.mock_data = 1
    status = TransitionStatus(signal=signal, transitions=[1, 2, 3], strict=False)
    assert status.done is False
    # Does not have to wait
    signal._read_pv.mock_data = 3
    signal._read_pv.mock_data = 2
    signal._read_pv.mock_data = 3
    status.wait(timeout=1)
    assert status.done is True
    assert status.success is True
    # Test with various transitions
    status = TransitionStatus(signal=signal, transitions=[1, 2, 3], strict=True)
    for transition in transitions:
        signal._read_pv.mock_data = transition
    if expected_done:
        status.wait(timeout=1)
        assert status.done is True
        assert status.success is expected_success
    else:
        with pytest.raises(WaitTimeoutError):
            status.wait(timeout=1)
        assert status.done is False
        assert status.success is False


def test_patched_status_objects():
    """Test the patched Status objects in ophyd_devices that improve error handling."""

    # StatusBase & AndStatus
    st = StatusBase()
    st2 = StatusBase()
    and_st = st & st2
    assert st in and_st
    assert isinstance(and_st, AndStatus)
    st.set_exception(ValueError("test error"))
    with pytest.raises(ValueError):
        and_st.wait(timeout=10)

    # DeviceStatus & Status
    dev = Device(name="device")
    dev_status = DeviceStatus(device=dev)

    st = Status()
    and_st = st & dev_status
    assert dev_status.device == dev
    dev_status.set_exception(RuntimeError("device error"))
    with pytest.raises(RuntimeError):
        and_st.wait(timeout=10)

    # Combine DeviceStatus with StatusBase and form AndStatus
    st = StatusBase(obj=dev)
    assert st.obj == dev
    dev_st = DeviceStatus(device=dev)
    combined_st = st & dev_st
    st.set_finished()
    dev_st.set_exception(RuntimeError("combined error"))
    with pytest.raises(RuntimeError):
        combined_st.wait(timeout=10)

    # SubscriptionStatus
    sig = Signal(name="test_signal", value=0)

    def _cb(*args, **kwargs):
        pass

    sub_st = SubscriptionStatus(sig, callback=_cb)
    sub_st.set_exception(ValueError("subscription error"))
    with pytest.raises(ValueError):
        sub_st.wait(timeout=10)
    assert sub_st.done is True
    assert sub_st.success is False

    # MoveStatus, here the default for call_stop_on_failure is True
    class Positioner(Device):
        SUB_READBACK = "readback"
        setpoint = Signal(name="setpoint", value=0)
        readback = Signal(name="readback", value=0)

        @property
        def position(self):
            return self.readback.get()

        def stop(self):
            pass

    pos = Positioner(name="positioner")
    move_st = MoveStatus(pos, target=10)
    with mock.patch.object(pos, "stop") as mock_stop:
        move_st.set_exception(RuntimeError("move error"))
        mock_stop.assert_called_once()
        with pytest.raises(RuntimeError):
            move_st.wait(timeout=10)
        assert move_st.done is True
        assert move_st.success is False


class Positioner(Device):
    SUB_READBACK = "readback"
    setpoint = Signal(name="setpoint", value=0)
    readback = Signal(name="readback", value=0)

    @property
    def position(self):
        return self.readback.get()

    def stop(self):
        pass


@pytest.mark.parametrize(
    ("factory", "expected_compact"),
    [
        pytest.param(
            lambda: StatusBase(timeout=0.01, description="base timed out"),
            "base timed out",
            id="statusbase",
        ),
        pytest.param(
            lambda: Status(timeout=0.01, description="status timed out"),
            "status timed out",
            id="status",
        ),
        pytest.param(
            lambda: DeviceStatus(
                Device(name="device"), timeout=0.01, description="device timed out"
            ),
            "device timed out",
            id="devicestatus",
        ),
        pytest.param(
            lambda: MoveStatus(
                Positioner(name="positioner"), target=10, timeout=0.01, description="move timed out"
            ),
            "move timed out",
            id="movestatus",
        ),
        pytest.param(
            lambda: TaskStatus(Device(name="device"), timeout=0.01, description="task timed out"),
            "task timed out",
            id="taskstatus",
        ),
        pytest.param(
            lambda: SubscriptionStatus(
                Signal(name="sig", value=0),
                callback=lambda *args, **kwargs: False,
                timeout=0.01,
                run=False,
                description="subscription timed out",
            ),
            "subscription timed out",
            id="subscriptionstatus",
        ),
    ],
)
def test_all_patched_status_types_raise_structured_timeout(factory, expected_compact):
    """All patched timeout-capable status types should raise structured timeout errors."""
    status = factory()

    with pytest.raises(StatusTimeoutErrorWithErrorInfo) as exc_info:
        status.wait(timeout=1)

    assert status.exception() is exc_info.value
    assert isinstance(exc_info.value, ExceptionWithErrorInfo)
    assert "Status initialization traceback" in exc_info.value.error_info.error_message
    assert exc_info.value.error_info.exception_type == "StatusTimeoutError"
    assert expected_compact in exc_info.value.error_info.compact_error_message


@pytest.mark.parametrize(
    ("left_factory", "right_factory"),
    [
        pytest.param(
            lambda: StatusBase(timeout=0.5, description="custom timeout"),
            lambda: StatusBase(),
            id="custom-custom",
        ),
        pytest.param(
            lambda: StatusBase(), lambda: OphydStatusBase(timeout=0.5), id="custom-ophydstatusbase"
        ),
        pytest.param(
            lambda: StatusBase(), lambda: OphydStatus(timeout=0.5), id="custom-ophydstatus"
        ),
        pytest.param(
            lambda: StatusBase(timeout=0.5, description="custom timeout"),
            lambda: OphydDeviceStatus(Device(name="device")),
            id="custom-ophyddevicestatus",
        ),
        pytest.param(
            lambda: StatusBase(),
            lambda: OphydMoveStatus(Positioner(name="positioner"), target=10, timeout=0.5),
            id="custom-ophydmovestatus",
        ),
    ],
)
def test_and_status_works_with_plain_ophyd_status_objects(left_factory, right_factory):
    """Composite statuses should work with both patched and plain ophyd status objects."""
    left = left_factory()
    right = right_factory()
    combined = left & right

    with pytest.raises(Exception) as exc_info:
        combined.wait(timeout=1)

    assert combined.done is True
    assert combined.success is False
    assert isinstance(exc_info.value, ExceptionWithErrorInfo)


@pytest.fixture(scope="function")
def mock_device_with_initial_value():
    with patched_device(EpicsMotor, _mock_pv_initial_value=2, name="motor") as mtr:
        yield mtr


def test_mock_device_initial_value(mock_device_with_initial_value: EpicsMotor):
    mtr = mock_device_with_initial_value
    assert mtr.velocity.get() == 2
