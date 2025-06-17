"""Utility handler to run tasks (function, conditions) in an asynchronous fashion."""

import ctypes
import operator
import threading
import traceback
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Literal

from bec_lib.file_utils import get_full_path
from bec_lib.logger import bec_logger
from bec_lib.utils.import_utils import lazy_import_from
from ophyd import Device, Signal
from ophyd.status import AndStatus, DeviceStatus, MoveStatus, Status, StatusBase, SubscriptionStatus

if TYPE_CHECKING:  # pragma: no cover
    from bec_lib.messages import ScanStatusMessage
else:
    # TODO: put back normal import when Pydantic gets faster
    ScanStatusMessage = lazy_import_from("bec_lib.messages", ("ScanStatusMessage",))


__all__ = [
    "CompareStatus",
    "TransitionStatus",
    "AndStatus",
    "DeviceStatus",
    "MoveStatus",
    "Status",
    "StatusBase",
    "SubscriptionStatus",
]

logger = bec_logger.logger

set_async_exc = ctypes.pythonapi.PyThreadState_SetAsyncExc

OP_MAP = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


class CompareStatus(SubscriptionStatus):
    """
    Status class to compare a signal value against a given value.
    The comparison is done using the specified operation, which can be one of
    '==', '!=', '<', '<=', '>', '>='. If the value is a string, only '==' and '!=' are allowed.
    The status is finished when the comparison is true.

    Args:
        signal: The device signal to compare.
        value: The value to compare against.
        operation: The operation to use for comparison. Defaults to '=='.
        event_type: The type of event to trigger on comparison. Defaults to None (default sub).
        timeout: The timeout for the status. Defaults to None (indefinite).
        settle_time: The time to wait for the signal to settle before comparison. Defaults to 0.
        run: Whether to run the status callback on creation or not. Defaults to True.
    """

    def __init__(
        self,
        signal: Signal,
        value: float | int | str,
        *,
        operation: Literal["==", "!=", "<", "<=", ">", ">="] = "==",
        event_type=None,
        timeout: float = None,
        settle_time: float = 0,
        run: bool = True,
    ):
        if isinstance(value, str):
            if operation not in ("==", "!="):
                raise ValueError(
                    f"Invalid operation: {operation} for string comparison. Must be '==' or '!='."
                )
        if operation not in ("==", "!=", "<", "<=", ">", ">="):
            raise ValueError(
                f"Invalid operation: {operation}. Must be one of '==', '!=', '<', '<=', '>', '>='."
            )
        self._signal = signal
        self._value = value
        self._operation = operation
        super().__init__(
            device=signal,
            callback=self._compare_callback,
            timeout=timeout,
            settle_time=settle_time,
            event_type=event_type,
            run=run,
        )

    def _compare_callback(self, value, **kwargs) -> bool:
        """Callback for subscription status"""
        return OP_MAP[self._operation](value, self._value)


class TransitionStatus(SubscriptionStatus):
    """
    Status class to monitor transitions of a signal value through a list of specified transitions.
    The status is finished when all transitions have been observed in order. The keyword argument
    `strict` determines whether the transitions must occur in strict order or not.
    If `raise_states` is provided, the status will raise an exception if the signal value matches
    any of the values in `raise_states`.

    Args:
        signal: The device signal to monitor.
        transitions: A list of values to transition through.
        strict: Whether the transitions must occur in strict order. Defaults to True.
        raise_states: A list of values that will raise an exception if encountered. Defaults to None.
        run: Whether to run the status callback on creation or not. Defaults to True.
        event_type: The type of event to trigger on transition. Defaults to None (default sub).
        timeout: The timeout for the status. Defaults to None (indefinite).
        settle_time: The time to wait for the signal to settle before comparison. Defaults to 0.
    """

    def __init__(
        self,
        signal: Signal,
        transitions: list[float | int | str],
        *,
        strict: bool = True,
        raise_states: list[float | int | str] | None = None,
        run: bool = True,
        event_type=None,
        timeout: float = None,
        settle_time: float = 0,
    ):
        self._signal = signal
        if not isinstance(transitions, list):
            raise ValueError(f"Transitions must be a list of values. Received: {transitions}")
        self._transitions = transitions
        self._index = 0
        self._strict = strict
        self._raise_states = raise_states if raise_states else []
        super().__init__(
            device=signal,
            callback=self._compare_callback,
            timeout=timeout,
            settle_time=settle_time,
            event_type=event_type,
            run=run,
        )

    def _compare_callback(self, old_value, value, **kwargs) -> bool:
        """Callback for subscription Status"""
        if value in self._raise_states:
            self.set_exception(
                ValueError(
                    f"Transition raised an exception: {value}. "
                    f"Expected transitions: {self._transitions}."
                )
            )
            return False
        if self._index == 0:
            if value == self._transitions[0]:
                self._index += 1
        else:
            if self._strict:
                if (
                    old_value == self._transitions[self._index - 1]
                    and value == self._transitions[self._index]
                ):
                    self._index += 1
            else:
                if value == self._transitions[self._index]:
                    self._index += 1
        return self._is_finished()

    def _is_finished(self) -> bool:
        """Check if the status is finished"""
        return self._index >= len(self._transitions)


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
    def state(self) -> str:
        """Get the state of the task"""
        return self._state.value

    @state.setter
    def state(self, value: TaskState):
        self._state = TaskState(value)

    @property
    def task_id(self) -> str:
        """Get the task ID"""
        return self._task_id


class TaskHandler:
    """Handler to manage asynchronous tasks"""

    def __init__(self, parent: Device):
        """Initialize the handler"""
        self._tasks = {}
        self._parent = parent
        self._lock = threading.RLock()

    def submit_task(
        self,
        task: Callable,
        task_args: tuple | None = None,
        task_kwargs: dict | None = None,
        run: bool = True,
    ) -> TaskStatus:
        """Submit a task to the task handler.

        Args:
            task: The task to run.
            run: Whether to run the task immediately.
        """
        task_args = task_args if task_args else ()
        task_kwargs = task_kwargs if task_kwargs else {}
        task_status = TaskStatus(device=self._parent)
        thread = threading.Thread(
            target=self._wrap_task,
            args=(task, task_args, task_kwargs, task_status),
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
        task_status.state = TaskState.RUNNING
        thread.start()

    def _wrap_task(
        self, task: Callable, task_args: tuple, task_kwargs: dict, task_status: TaskStatus
    ):
        """Wrap the task in a function"""
        try:
            task(*task_args, **task_kwargs)
        except TimeoutError as exc:
            content = traceback.format_exc()
            logger.warning(
                (
                    f"Timeout Exception in task handler for task {task_status.task_id},"
                    f" Traceback: {content}"
                )
            )
            task_status.state = TaskState.TIMEOUT
            task_status.set_exception(exc)
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
            task_status.state = TaskState.KILLED
            task_status.set_exception(exc)
        except Exception as exc:  # pylint: disable=broad-except
            content = traceback.format_exc()
            logger.warning(
                f"Exception in task handler for task {task_status.task_id}, Traceback: {content}"
            )
            task_status.state = TaskState.ERROR
            task_status.set_exception(exc)
        else:
            task_status.state = TaskState.COMPLETED
            task_status.set_finished()
        finally:
            with self._lock:
                self._tasks.pop(task_status.task_id, None)

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
            if res > 1:
                set_async_exc(ident, None)
                logger.warning(f"Exception raise while kille Thread {ident}; return value: {res}")
        except Exception as e:  # pylint: disable=broad-except
            logger.warning(f"Exception raised while killing thread {ident}: {e}")

    def shutdown(self):
        """Shutdown all tasks of task handler"""
        with self._lock:
            for info in self._tasks.values():
                self.kill_task(info[0])


class FileHandler:
    """Utility class for file operations."""

    def get_full_path(
        self, scan_status_msg: ScanStatusMessage, name: str, create_dir: bool = True
    ) -> str:
        """Get the file path.

        Args:
            scan_info_msg: The scan info message.
            name: The name of the file.
            create_dir: Whether to create the directory.
        """
        return get_full_path(scan_status_msg=scan_status_msg, name=name, create_dir=create_dir)
