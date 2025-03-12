import threading
import time

import pytest
from ophyd import Device

from ophyd_devices.utils.psi_device_base_utils import (
    FileHandler,
    TaskHandler,
    TaskKilledError,
    TaskState,
    TaskStatus,
)


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
