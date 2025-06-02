import threading
import time

import numpy as np
import pytest
from bec_lib import messages
from ophyd import Device

from ophyd_devices.utils.bec_signals import (
    BECMessageSignal,
    DynamicSignal,
    FileEventSignal,
    PreviewSignal,
    ProgressSignal,
)
from ophyd_devices.utils.psi_device_base_utils import (
    FileHandler,
    TaskHandler,
    TaskKilledError,
    TaskState,
    TaskStatus,
)

# pylint: disable=protected-access
# pylint: disable=redefined-outer-name

##########################################
#########  Test Task Handler  ############
##########################################


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
    status = TaskStatus(device=device)
    assert status.device.name == "device"
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
                "signal_metadata": None,
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


def test_utils_dynamic_signal():
    """Test DynamicSignal"""
    dev = Device(name="device")
    signal = DynamicSignal(name="dynamic_signal", signals=["sig1", "sig2"], value=None, parent=dev)
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
                "signal_metadata": None,
            },
        }
    }

    # Put works with Message
    msg_dict = {"sig1": {"value": 1}, "sig2": {"value": 2}}
    msg = messages.DeviceMessage(signals=msg_dict)
    signal.put(msg)
    reading = signal.read()
    assert reading[signal.name]["value"] == msg
    # Set works with dict
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
                "role": "file event",
                "enabled": True,
                "rpc_access": False,
                "signals": [("file_event_signal", 5)],
                "signal_metadata": None,
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
                "signal_metadata": None,
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
