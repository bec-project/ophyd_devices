"""Utility handler to run tasks (function, conditions) in an asynchronous fashion."""

import ctypes
import operator
import threading
import traceback
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Callable, Literal, Union

from bec_lib.file_utils import get_full_path
from bec_lib.logger import bec_logger
from bec_lib.utils.import_utils import lazy_import_from
from ophyd.status import DeviceStatus as _DeviceStatus
from ophyd.status import MoveStatus as _MoveStatus
from ophyd.status import Status as _Status
from ophyd.status import StatusBase as _StatusBase

if TYPE_CHECKING:  # pragma: no cover
    from bec_lib.messages import ScanStatusMessage
    from ophyd import Device, Signal
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


class StatusBase(_StatusBase):
    """Base class for all status objects."""

    def __init__(
        self,
        obj: Union["Device", None] = None,
        *,
        timeout=None,
        settle_time=0,
        done=None,
        success=None,
    ):
        self.obj = obj
        super().__init__(timeout=timeout, settle_time=settle_time, done=done, success=success)

    def __and__(self, other):
        """Returns a new 'composite' status object, AndStatus"""
        return AndStatus(self, other)


class AndStatus(StatusBase):
    """
    A Status that has composes two other Status objects using logical and.
    If any of the two Status objects fails, the combined status will fail
    with the exception of the first Status to fail.

    Args:
        left (StatusBase): Left status object.
        right (StatusBase): Right status object.

    Examples:
        >>> status1 = StatusBase(device1)
        >>> status2 = StatusBase(device2)
        >>> status3 = StatusBase(device3)
        >>> combined_status = AndStatus(status1, status2)
        >>> combined_status = status1 & status2
        >>> combined_status = status1 & status2 & status3
    """

    def __init__(self, left, right, **kwargs):
        self.left = left
        self.right = right
        super().__init__(**kwargs)
        self._trace_attributes["left"] = self.left._trace_attributes
        self._trace_attributes["right"] = self.right._trace_attributes

        def inner(status):
            with self._lock:
                if self._externally_initiated_completion:
                    return

                # Return if status is already done..
                if self.done:
                    return

                with status._lock:
                    if status.done and not status.success:
                        self.set_exception(status.exception())  # st._exception
                        return
                if self.left.done and self.right.done and self.left.success and self.right.success:
                    self.set_finished()

        self.left.add_callback(inner)
        self.right.add_callback(inner)

    def __repr__(self):
        return "({self.left!r} & {self.right!r})".format(self=self)

    def __str__(self):
        return "{0}(done={1.done}, " "success={1.success})" "".format(self.__class__.__name__, self)

    def __contains__(self, status) -> bool:
        for child in [self.left, self.right]:
            if child == status:
                return True
            if isinstance(child, AndStatus):
                if status in child:
                    return True

        return False


class Status(_Status):
    """Thin wrapper around StatusBase to add __and__ operator."""

    def __and__(self, other):
        """Returns a new 'composite' status object, AndStatus"""
        return AndStatus(self, other)


class DeviceStatus(_DeviceStatus):
    """Thin wrapper around DeviceStatus to add __and__ operator."""

    def __and__(self, other):
        """Returns a new 'composite' status object, AndStatus"""
        return AndStatus(self, other)


class MoveStatus(_MoveStatus):
    """Thin wrapper around MoveStatus to ensure __and__ operator and stop on failure."""

    def __and__(self, other):
        """Returns a new 'composite' status object, AndStatus"""
        return AndStatus(self, other)


class SubscriptionStatus(StatusBase):
    """Subscription status implementation based on wrapped StatusBase implementation."""

    def __init__(
        self,
        obj: Union["Device", "Signal"],
        callback: Callable,
        event_type=None,
        timeout=None,
        settle_time=None,
        run=True,
    ):
        # Store device and attribute information
        self.callback = callback
        self.obj = obj
        # Start timeout thread in the background
        super().__init__(obj=obj, timeout=timeout, settle_time=settle_time)

        self.obj.subscribe(self.check_value, event_type=event_type, run=run)

    def check_value(self, *args, **kwargs):
        """Update the status object"""
        try:
            success = self.callback(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in SubscriptionStatus callback: {e}")
            self.set_exception(e)
            return
        if success:
            self.set_finished()

    def set_finished(self):
        """Mark as finished successfully."""
        self.obj.clear_sub(self.check_value)
        super().set_finished()

    def _handle_failure(self):
        """Clear subscription on failure, run callbacks through super()"""
        self.obj.clear_sub(self.check_value)
        return super()._handle_failure()


class CompareStatus(SubscriptionStatus):
    """
    Status to compare a signal value against a given value.
    The comparison is done using the specified operation, which can be one of
    '==', '!=', '<', '<=', '>', '>='. If the value is a string, only '==' and '!=' are allowed.
    One may also define a value or list of values that will result in an exception if encountered.
    The status is finished when the comparison is either true or an exception is raised.

    Args:
        signal (Signal): The signal to monitor.
        value (float | int | str): The target value to compare against.
        operation_success (str, optional): The comparison operation for success. Defaults to '=='.
        failure_value (float | int | str | list[float | int | str] | None, optional):
            A value or list of values that will trigger an exception if encountered. Defaults to None.
        operation_failure (str, optional): The comparison operation for failure values. Defaults to '=='.
        event_type (int, optional): The event type to subscribe to. Defaults to None.
        timeout (float, optional): Timeout for the status. Defaults to None.
        settle_time (float, optional): Settle time before checking the status. Defaults to 0.
        run (bool, optional): Whether to start the status immediately. Defaults to True
    """

    def __init__(
        self,
        signal: "Signal",
        value: float | int | str,
        *,
        operation_success: Literal["==", "!=", "<", "<=", ">", ">="] = "==",
        failure_value: float | int | str | list[float | int | str] | None = None,
        operation_failure: Literal["==", "!=", "<", "<=", ">", ">="] = "==",
        timeout: float = None,
        settle_time: float = 0,
        run: bool = True,
        event_type=None,
    ):
        if isinstance(value, str):
            if operation_success not in ("==", "!=") or operation_failure not in ("==", "!="):
                raise ValueError(
                    f"Invalid operation_success: {operation_success} for string comparison. Must be '==' or '!='."
                )
        if operation_success not in ("==", "!=", "<", "<=", ">", ">="):
            raise ValueError(
                f"Invalid operation_success: {operation_success}. Must be one of '==', '!=', '<', '<=', '>', '>='."
            )
        self._signal = signal
        self._value = value
        self._operation_success = operation_success
        self._operation_failure = operation_failure
        self.op_map = OP_MAP
        if failure_value is None:
            self._failure_values = []
        elif isinstance(failure_value, (float, int, str)):
            self._failure_values = [failure_value]
        elif isinstance(failure_value, (list, tuple)):
            self._failure_values = failure_value
        else:
            raise ValueError(
                f"failure_value must be a float, int, str, list or None. Received: {failure_value}"
            )
        super().__init__(
            obj=signal,
            callback=self._compare_callback,
            timeout=timeout,
            settle_time=settle_time,
            event_type=event_type,
            run=run,
        )

    def _compare_callback(self, value: any, **kwargs) -> bool:
        """
        Callback for subscription status

        Args:
            value (any): Current value of the signal

        Returns:
            bool: True if comparison is successful, False otherwise.
        """
        try:
            if isinstance(value, list):
                raise ValueError(f"List values are not supported. Received value: {value}")
            if any(
                self.op_map[self._operation_failure](value, failure_value)
                for failure_value in self._failure_values
            ):
                raise ValueError(
                    f"CompareStatus for signal {self._signal.name} "
                    f"did not reach the desired state {self._operation_success} {self._value}. "
                    f"But instead reached {value}, which is in list of failure values: {self._failure_values}"
                )
            return self.op_map[self._operation_success](value, self._value)
        except Exception as e:
            logger.error(f"Error in CompareStatus callback: {e}")
            self.set_exception(e)
            return False


class TransitionStatus(SubscriptionStatus):
    """
    Status to monitor transitions of a signal value through a list of specified transitions.
    The status is finished when all transitions have been observed in order. The keyword argument
    `strict` determines whether the transitions must occur in strict order or not. The strict option
    only becomes relevant once the first transition has been observed.
    If `failure_states` is provided, the status will raise an exception if the signal value matches
    any of the values in `failure_states`.

    Args:
        signal (Signal): The signal to monitor.
        transitions (list[float | int | str]): List of values representing the transitions to observe.
        strict (bool, optional): Whether to enforce strict order of transitions. Defaults to True.
        failure_states (list[float | int | str] | None, optional):
            A list of values that will trigger an exception if encountered. Defaults to None.
        run (bool, optional): Whether to start the status immediately. Defaults to True.
        event_type (int, optional): The event type to subscribe to. Defaults to None.
        timeout (float, optional): Timeout for the status. Defaults to None.
        settle_time (float, optional): Settle time before checking the status. Defaults to 0.

    Notes:
        The 'strict' option does not raise if transitions are observed which are out of order.
        It only determines whether a transition is accepted if it is observed from the
        previous value in the list of transitions to the next value.
        For example, with strict=True and transitions=[1, 2, 3], the sequence
        0 -> 1 -> 2 -> 3 is accepted, but 0 -> 1 -> 3 -> 2 -> 3 is not and the status
        will not complete. With strict=False, both sequences are accepted.
        However, with strict=True, the sequence 0 -> 1 -> 3 -> 1 -> 2 -> 3 is accepted.
        To raise an exception if an out-of-order transition is observed, use the
        `failure_states` keyword argument.
    """

    def __init__(
        self,
        signal: "Signal",
        transitions: list[float | int | str],
        *,
        strict: bool = True,
        failure_states: list[float | int | str] | None = None,
        run: bool = True,
        timeout: float = None,
        settle_time: float = 0,
        event_type=None,
    ):
        self._signal = signal
        self._transitions = tuple(transitions)
        if not transitions:
            raise ValueError("Transitions {transitions}must contain at least one value")
        self._index = 0
        self._strict = strict
        self._failure_states = failure_states if failure_states else []
        super().__init__(
            obj=signal,
            callback=self._compare_callback,
            timeout=timeout,
            settle_time=settle_time,
            event_type=event_type,
            run=run,
        )

    def _compare_callback(self, old_value: any, value: any, **kwargs) -> bool:
        """
        Callback for subscription Status

        Args:
            old_value (any): Previous value of the signal
            value (any): Current value of the signal

        Returns:
            bool: True if all transitions have been observed, False otherwise.
        """
        try:
            if value in self._failure_states:
                raise ValueError(
                    f"Transition Status for {self._signal.name} resulted in a value: {value}. "
                    f"marked to raise {self._failure_states}. Expected transitions: {self._transitions}."
                )
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
            return self._index >= len(self._transitions)
        except Exception as e:
            # Catch any exception if the value comparison fails, e.g. value is numpy array
            logger.error(f"Error in TransitionStatus callback: {e}")
            self.set_exception(e)
            return False


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


class TaskStatus(StatusBase):
    """Thin wrapper around StatusBase to add information about tasks"""

    def __init__(
        self,
        obj: Union["Device", "Signal"],
        *,
        timeout=None,
        settle_time=0,
        done=None,
        success=None,
    ):
        super().__init__(
            obj=obj, timeout=timeout, settle_time=settle_time, done=done, success=success
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

    def __init__(self, parent: "Device"):
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
        task_status = TaskStatus(self._parent)
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
