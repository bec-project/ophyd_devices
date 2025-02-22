""" Utility handler to run tasks (function, conditions) in an asynchronous fashion."""

import ctypes
import threading
import traceback
import uuid
from enum import Enum
from typing import TYPE_CHECKING

from bec_lib.file_utils import get_full_file_path
from bec_lib.logger import bec_logger
from bec_lib.utils.import_utils import lazy_import_from
from ophyd import Device, DeviceStatus, StatusBase

if TYPE_CHECKING:
    from bec_lib.messages import ScanStatusMessage
else:
    # TODO: put back normal import when Pydantic gets faster
    ScanStatusMessage = lazy_import_from("bec_lib.messages", ("ScanStatusMessage",))


logger = bec_logger.logger

set_async_exc = ctypes.pythonapi.PyThreadState_SetAsyncExc


class TaskState(str, Enum):
    """Possible task states"""

    NOT_STARTED = "not_started"
    RUNNING = "running"
    TIMEOUT = "timeout"
    ERROR = "error"
    COMPLETED = "completed"
    KILLED = "killed"


class TaskKilledError(Exception):
    """Exception raised when a task thread is killed"""


class TaskStatus(DeviceStatus):
    """Thin wrapper around StatusBase to add information about tasks"""

    def __init__(self, device: Device, *, timeout=None, settle_time=0, done=None, success=None):
        super().__init__(
            device=device, timeout=timeout, settle_time=settle_time, done=done, success=success
        )
        self._state = TaskState.NOT_STARTED
        self._task_id = str(uuid.uuid4())

    @property
    def exc(self) -> Exception:
        """Get the exception of the task"""
        return self.exception()

    @property
    def state(self) -> str:
        """Get the state of the task"""
        return self._state.value

    @state.setter
    def state(self, value: TaskState):
        self._state = value

    @property
    def task_id(self) -> bool:
        """Get the task ID"""
        return self._task_id


class TaskHandler:
    """Handler to manage asynchronous tasks"""

    def __init__(self, parent: Device):
        """Initialize the handler"""
        self._tasks = {}
        self._parent = parent

    def submit_task(self, task: callable, run: bool = True) -> TaskStatus:
        """Submit a task to the task handler.

        Args:
            task: The task to run.
            run: Whether to run the task immediately.
        """
        task_status = TaskStatus(device=self._parent)
        thread = threading.Thread(
            target=self._wrap_task,
            args=(task, task_status),
            name=f"task {task_status.task_id}",
            daemon=True,
        )
        self._tasks.update({task_status.task_id: (task_status, thread)})
        if run is True:
            self.start_task(task_status)
        return task_status

    def start_task(self, task_status: TaskStatus) -> None:
        """Start a task,

        Args:
            task_status: The task status object.
        """
        thread = self._tasks[task_status.task_id][1]
        if thread.is_alive():
            logger.warning(f"Task with ID {task_status.task_id} is already running.")
            return
        thread.start()
        task_status.state = TaskState.RUNNING

    def _wrap_task(self, task: callable, task_status: TaskStatus):
        """Wrap the task in a function"""
        try:
            task()
        except TimeoutError as exc:
            content = traceback.format_exc()
            logger.warning(
                (
                    f"Timeout Exception in task handler for task {task_status.task_id},"
                    f" Traceback: {content}"
                )
            )
            task_status.set_exception(exc)
            task_status.state = TaskState.TIMEOUT
        except TaskKilledError as exc:
            exc = exc.__class__(
                f"Task {task_status.task_id} was killed. ThreadID:"
                f" {self._tasks[task_status.task_id][1].ident}"
            )
            content = traceback.format_exc()
            logger.warning(
                (
                    f"TaskKilled Exception in task handler for task {task_status.task_id},"
                    f" Traceback: {content}"
                )
            )
            task_status.set_exception(exc)
            task_status.state = TaskState.KILLED
        except Exception as exc:  # pylint: disable=broad-except
            content = traceback.format_exc()
            logger.warning(
                f"Exception in task handler for task {task_status.task_id}, Traceback: {content}"
            )
            task_status.set_exception(exc)
            task_status.state = TaskState.ERROR
        else:
            task_status.set_finished()
            task_status.state = TaskState.COMPLETED
        finally:
            self._tasks.pop(task_status.task_id)

    def kill_task(self, task_status: TaskStatus) -> None:
        """Kill the thread

        task_status: The task status object.
        """
        thread = self._tasks[task_status.task_id][1]
        exception_cls = TaskKilledError

        ident = ctypes.c_long(thread.ident)
        exc = ctypes.py_object(exception_cls)
        try:
            res = set_async_exc(ident, exc)
            if res == 0:
                raise ValueError("Invalid thread ID")
            elif res > 1:
                set_async_exc(ident, None)
                logger.warning(f"Exception raise while kille Thread {ident}; return value: {res}")
        except Exception as e:  # pylint: disable=broad-except
            logger.warning(f"Exception raised while killing thread {ident}: {e}")

    def shutdown(self):
        """Shutdown all tasks of task handler"""
        for info in self._tasks.values():
            self.kill_task(info[0])
        self._tasks.clear()


class FileHandler:
    """Utility class for file operations."""

    def get_file_path(
        self, scan_status_msg: ScanStatusMessage, name: str, create_dir: bool = True
    ) -> str:
        """Get the file path.

        Args:
            scan_info_msg: The scan info message.
            name: The name of the file.
            create_dir: Whether to create the directory.
        """
        return get_full_file_path(scan_status_msg=scan_status_msg, name=name, create_dir=create_dir)
