"""Utility handler to run tasks (function, conditions) in an asynchronous fashion."""

from __future__ import annotations

import ctypes
import operator
import threading
import traceback
import uuid
from collections.abc import Iterable
from contextvars import copy_context
from enum import Enum
from itertools import chain
from time import monotonic
from typing import TYPE_CHECKING, Callable, Literal

from bec_lib import messages
from bec_lib.bec_errors import ExceptionWithErrorInfo
from bec_lib.file_utils import get_full_path
from bec_lib.logger import bec_logger
from bec_lib.utils.import_utils import lazy_import_from
from ophyd.status import AndStatus as _AndStatus
from ophyd.status import DeviceStatus as _DeviceStatus
from ophyd.status import MoveStatus as _MoveStatus
from ophyd.status import Status as _Status
from ophyd.status import StatusBase as _StatusBase
from ophyd.utils import StatusTimeoutError
from ophyd.utils.errors import InvalidState, WaitTimeoutError

from .ophyd_callback_patch import callback_name, object_name

if TYPE_CHECKING:  # pragma: no cover
    from bec_lib.messages import ScanStatusMessage
    from ophyd import Device, Signal
else:
    # TODO: put back normal import when Pydantic gets faster
    ScanStatusMessage = lazy_import_from("bec_lib.messages", ("ScanStatusMessage",))


__all__ = [
    "CompareStatus",
    "ExceptionStatus",
    "TransitionStatus",
    "AndStatus",
    "DeviceStatus",
    "MoveStatus",
    "Status",
    "StatusBase",
    "SubscriptionStatus",
    "SequenceStatus",
    "all_statuses",
    "release_statuses",
]

logger = bec_logger.logger


def _log_callback_exception(status, exc: Exception) -> None:
    """Retain the traceback in callback logs even when only the message is forwarded."""
    logger.error(
        f"Error in {type(status).__name__} callback {callback_name(status.callback)} "
        f"for {object_name(status.obj)}: {exc}\n{traceback.format_exc()}"
    )


set_async_exc = ctypes.pythonapi.PyThreadState_SetAsyncExc

OP_MAP = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


class StatusTimeoutErrorWithErrorInfo(ExceptionWithErrorInfo, TimeoutError):
    """Status timeout exception that carries structured BEC error info."""


def _capture_status_initialization_traceback() -> tuple[traceback.FrameSummary | None, str]:
    """Capture the stack at status creation time."""
    stack = traceback.extract_stack()
    trimmed_stack = stack[:-1]
    frame = None
    while trimmed_stack:
        frame = trimmed_stack[-1]
        if frame.filename != __file__:
            break
        trimmed_stack.pop()
    return frame, "".join(traceback.format_list(trimmed_stack)).rstrip()


class _StatusTimeoutDiagnostics:
    """Enhance timeout failures with the status creation traceback."""

    def __init__(
        self, status_initialization_traceback: str | None = None, description: str | None = None
    ):
        self._status = None
        frame, traceback_str = _capture_status_initialization_traceback()
        self._status_initialization_traceback = status_initialization_traceback or traceback_str
        self._status_initialization_frame = frame
        self._description = description

    def bind(self, status: _StatusBase) -> None:
        """
        Bind the diagnostics to a status object.

        Args:
            status (_StatusBase): The status object to bind to.
        """
        self._status = status

    def build_timeout_error_message(self) -> str:
        """
        Build a detailed error message for a timeout error with the status object and
        the status initialization traceback.

        Returns:
            str: The detailed error message.
        """
        message = f"Status {self._status!r} failed to complete in specified timeout."
        if self._status_initialization_traceback:
            message = (
                f"{message}\n\n"
                "Status initialization traceback (most recent call last):\n"
                f"{self._status_initialization_traceback}"
            )
        return message

    def build_timeout_error_info(self) -> messages.ErrorInfo:
        """
        Build a structured error info object for a timeout error with the status object and
        the status initialization traceback.

        Returns:
            messages.ErrorInfo: The structured error info object.
        """
        device_name = None
        signal_name = None

        if hasattr(self._status, "device") and getattr(self._status, "device", None) is not None:
            device = self._status.device  # type: ignore
            device_root = getattr(device, "root", device)
            device_name = device_root.name
            signal_name = getattr(device, "dotted_name", None) or getattr(device, "name", None)
        elif hasattr(self._status, "obj") and getattr(self._status, "obj", None) is not None:
            obj = self._status.obj  # type: ignore
            device_root = getattr(obj, "root", obj)
            device_name = device_root.name
            signal_name = getattr(obj, "dotted_name", None) or getattr(obj, "name", None)

        compact_message = f"Status timeout for {device_name or self._status.__class__.__name__}"
        if self._status_initialization_frame:
            compact_message += f" in method '{self._status_initialization_frame.name}'"
        if signal_name and signal_name != device_name:
            compact_message += f" waiting for signal {signal_name}."
        if self._description:
            compact_message = f"{self._description}\n\n{compact_message}"

        return messages.ErrorInfo(
            error_message=self.build_timeout_error_message(),
            compact_error_message=compact_message,
            exception_type="StatusTimeoutError",
            device=device_name,
        )

    def new_timeout_exception(self) -> StatusTimeoutErrorWithErrorInfo:
        """
        Create a new StatusTimeoutErrorWithErrorInfo exception with the structured error info.
        """
        return StatusTimeoutErrorWithErrorInfo(self.build_timeout_error_info())


def _run_callbacks_with_diagnostics(
    status: _StatusBase, diagnostics: _StatusTimeoutDiagnostics | None
):
    """
    Set the Event and run the callbacks.

    This mirrors ophyd's implementation but preserves the status creation
    traceback when a timeout is raised on the background thread.
    """
    # pylint: disable=protected-access
    if status.timeout is None:
        timeout = None
    else:
        timeout = status.timeout + status.settle_time
    if not status._settled_event.wait(timeout):
        logger.warning(
            f"Status {status!r} failed to complete in specified timeout of {timeout} seconds. "
            "This may be due to a bug in the device or a slow operation."
        )
        with status._externally_initiated_completion_lock:
            if status._exception is None:
                if diagnostics is None:
                    status._exception = StatusTimeoutError(
                        f"Status {status!r} failed to complete in specified timeout."
                    )
                else:
                    status._exception = diagnostics.new_timeout_exception()
                # Seal the timeout before announcing it. Late cancellation must
                # not replace a terminal error already visible to another caller.
                status._externally_initiated_completion = True
    try:
        status._settled()
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception(f"Exception raised while running _settled() for status {status!r}: {exc}")
    with status._lock:
        status._event.set()
    if status._exception is not None:
        try:
            status._handle_failure()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception(
                f"Exception raised while running _handle_failure() for status {status!r}: {exc}"
            )
    for cb in status._callbacks:
        try:
            cb(status)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception(
                f"An error was raised on a background thread while running the callback {cb!r}({status!r}): {exc}"
            )
    status._callbacks.clear()


class StatusBase(_StatusBase):
    """Base class for all status objects."""

    _blocks_success = True

    def __init__(
        self,
        obj: Device | Signal | None = None,
        *,
        timeout=None,
        settle_time=0,
        done=None,
        success=None,
        description: str | None = None,
    ):
        self.obj = obj
        self._timeout_diagnostics = _StatusTimeoutDiagnostics(description=description)
        super().__init__(timeout=timeout, settle_time=settle_time, done=done, success=success)
        self._timeout_diagnostics.bind(self)

    def __and__(self, other):
        """Returns a new 'composite' status object, AndStatus"""
        return AndStatus(self, other)

    @property
    def blocks_success(self) -> bool:
        """Whether this status must resolve successfully for a composite to succeed."""
        return self._blocks_success

    def _cleanup(self) -> None:
        """Release resources held by the status once a composite no longer needs it."""
        return None

    def _run_callbacks(self):
        _run_callbacks_with_diagnostics(self, self._timeout_diagnostics)

    def set_exception(self, exc):
        """
        Preserve timeout causes using exception types accepted by Ophyd status storage.
        """
        if isinstance(exc, WaitTimeoutError):
            converted = TimeoutError(str(exc))
            converted.__cause__ = exc
            for note in getattr(exc, "__notes__", ()):
                converted.add_note(note)
            exc = converted
        elif isinstance(exc, StatusTimeoutError):
            original = exc
            exc = StatusTimeoutErrorWithErrorInfo(
                messages.ErrorInfo(
                    error_message=str(exc),
                    compact_error_message=str(exc),
                    exception_type=exc.__class__.__name__,
                )
            )
            exc.__cause__ = original
        return super().set_exception(exc)


def _status_failure(status: _StatusBase | None) -> Exception | None:
    """
    Find a committed failure before child callbacks or nested cleanup have finished.

    Read failure reservations without acquiring child locks: a native completion
    callback may already hold that child's lock while entering its parent.
    """
    pending = [] if status is None else [status]
    visited = set()
    while pending:
        child = pending.pop()
        if id(child) in visited:
            continue
        visited.add(id(child))
        error = child._exception
        if error is None and isinstance(child, AndStatus):
            error = child._completion_error
        if error is None and isinstance(child, SequenceStatus):
            error = child._sequence_error
        if isinstance(error, type) and issubclass(error, Exception):
            error = error()
        if error is not None:
            return error
        if child.done:
            continue
        if isinstance(child, SequenceStatus):
            if child._active_child is not None:
                pending.append(child._active_child)
        elif isinstance(child, (AndStatus, _AndStatus)):
            pending.extend((child.right, child.left))
    return None


class AndStatus(StatusBase):
    """
    Combine two statuses, retaining child failures through cancellation and cleanup.

    Child failure and explicit cancellation reserve the original error before
    releasing either child. Nested sequences/composites finish their owned cleanup
    before this composite reports that failure. Pending ExceptionStatus watchers
    do not block success and are detached when the required children succeed.
    Constructor timeout and settle-time behavior remain those of StatusBase.

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
        self._completion_started = False
        self._completion_error: Exception | None = None
        super().__init__(**kwargs)
        self._trace_attributes["left"] = self.left._trace_attributes
        self._trace_attributes["right"] = self.right._trace_attributes

        self.left.add_callback(self._child_finished)
        self.right.add_callback(self._child_finished)
        # A sequence or failure watcher may have committed its error while its
        # cleanup/callback is still pending. Do not wait for another child event.
        error = self._first_child_failure()
        if error is not None:
            self.set_exception(error)

    def _child_finished(self, _status: _StatusBase) -> None:
        """
        Reserve a terminal outcome before cleanup can invoke child callbacks again.
        """
        with self._lock:
            if self._completion_started or self._externally_initiated_completion or self.done:
                return
            error = self._first_child_failure()
            if error is None:
                if not self._required_statuses_succeeded():
                    return
                self._completion_started = True
        if error is not None:
            self.set_exception(error)
            return
        cleanup_error = None
        try:
            self._cleanup()
        except Exception as error:  # noqa: BLE001 - report resource cleanup failure.
            cleanup_error = error
        # A failure watcher may commit its error before its callback runs. Check
        # again after detaching it and before publishing successful completion.
        with self._lock:
            error = self._first_child_failure()
            if error is None:
                error = cleanup_error
            elif cleanup_error is not None:
                error.add_note(f"Composite cleanup also failed: {cleanup_error!r}")
            self._completion_error = error
        if error is None:
            super().set_finished()
        else:
            self._finish_failure(error)

    def _handle_failure(self) -> None:
        """
        Release owned work on constructor timeout as well as explicit cancellation.

        Constructor timeout retains native completion timing. Nested sequence cleanup
        may finish afterward; an owning sequence still waits for it when cancelling
        the timed-out composite's children.
        """
        with self._lock:
            cleanup = not self._completion_started
            if cleanup:
                self._completion_started = True
                self._completion_error = self._exception
        if cleanup:
            _cancel_statuses((self.left, self.right), self._exception)
        super()._handle_failure()

    def set_exception(self, exc: Exception | type[Exception]) -> None:
        """
        Fail after owned cleanup; repeated or reentrant cancellation keeps the first error.

        Args:
            exc (Exception | type[Exception]): Original failure or cancellation. A child
                failure already committed before this call takes precedence.
        """
        if isinstance(exc, type) and issubclass(exc, Exception):
            exc = exc()
        if not isinstance(exc, Exception):
            raise ValueError(f"Expected an Exception, got {exc!r}")
        with self._lock:
            if self._completion_started or self._externally_initiated_completion or self.done:
                return
            # Reentrant owner.stop() can arrive before a failed child's callback
            # because that child is still completing its own failure cleanup.
            error = self._first_child_failure()
            if error is None:
                error = exc
            self._completion_error = error
            self._completion_started = True
        self._finish_failure(error)

    def _finish_failure(self, error: Exception) -> None:
        """
        Cancel children outside the bookkeeping lock, then await their cleanup.
        """

        def complete(_status=None):
            with self._lock:
                # A native constructor timeout may have finalized the composite
                # while its children were still completing cleanup.
                if self.done or self._externally_initiated_completion:
                    return
            try:
                super(AndStatus, self).set_exception(error)
            except InvalidState:
                pass  # Another terminal completion won after the bookkeeping check.

        settled = _cancel_statuses((self.left, self.right), error)
        if settled is None:
            complete()
        else:
            settled.add_callback(complete)

    def _first_child_failure(self) -> Exception | None:
        """
        Inspect committed errors, including failures whose cleanup has not settled yet.
        """
        for child in (self.left, self.right):
            error = _status_failure(child)
            if error is not None:
                return error
        return None

    def __repr__(self):
        return "({self.left!r} & {self.right!r})".format(self=self)

    def __str__(self):
        return "{0}(done={1.done}, success={1.success})".format(self.__class__.__name__, self)

    def __contains__(self, status) -> bool:
        for child in [self.left, self.right]:
            if child == status:
                return True
            if isinstance(child, AndStatus):
                if status in child:
                    return True

        return False

    @property
    def blocks_success(self) -> bool:
        return self._child_blocks_success(self.left) or self._child_blocks_success(self.right)

    def _required_statuses_succeeded(self) -> bool:
        return all(
            not self._child_blocks_success(child) or (child.done and child.success)
            for child in (self.left, self.right)
        )

    def _cleanup(self) -> None:
        self._cleanup_child(self.left)
        self._cleanup_child(self.right)

    @staticmethod
    def _child_blocks_success(child) -> bool:
        return getattr(child, "blocks_success", True)

    @staticmethod
    def _cleanup_child(child) -> None:
        cleanup = getattr(child, "_cleanup", None)
        if cleanup is not None:
            cleanup()


def all_statuses(statuses: Iterable[_StatusBase]) -> _StatusBase:
    """
    Combine independent acknowledgements, succeeding immediately for an empty input.

    Args:
        statuses (Iterable[ophyd.status.StatusBase]): Statuses already started by their
            owners. A single status is returned unchanged; larger inputs use AndStatus,
            including its failure-watch and subscription-cleanup semantics. Pairwise
            construction keeps large collections below Python's recursion limit.

    Returns:
        ophyd.status.StatusBase: Combined acknowledgement, or an already-successful
            StatusBase when there is no work to wait for.
    """
    children = tuple(statuses)
    if any(not isinstance(child, _StatusBase) for child in children):
        raise TypeError("all_statuses requires status objects")
    if not children:
        ready = StatusBase()
        ready.set_finished()
        return ready
    if len(children) == 1:
        return children[0]
    required = tuple(child for child in children if getattr(child, "blocks_success", True))
    if not required:
        return _balanced_statuses(children)
    combined = _balanced_statuses(required)
    # Failure-only subtrees would otherwise succeed and detach their watchers
    # during construction. Keep each watcher attached to all required work.
    watched = tuple(
        AndStatus(combined, child)
        for child in children
        if not getattr(child, "blocks_success", True)
    )
    return _balanced_statuses(watched) if watched else combined


def _balanced_statuses(children: tuple[_StatusBase, ...]) -> _StatusBase:
    """
    Combine a nonempty collection without building a linear callback/cleanup stack.
    """
    while len(children) > 1:
        paired = []
        for index in range(0, len(children), 2):
            left = children[index]
            paired.append(
                AndStatus(left, children[index + 1]) if index + 1 < len(children) else left
            )
        children = tuple(paired)
    return children[0]


def release_statuses(statuses: Iterable[StatusBase], *, reason: str) -> None:
    """
    Fail unfinished watchers and release their subscriptions after setup fails.

    Use when an operation fails before returning its watchers to the owning
    sequence. Already-finished watchers still have their subscriptions released.
    Concurrent completion is tolerated; other errors propagate to the caller.

    Args:
        statuses (Iterable[StatusBase]): Watchers created by the failed operation,
            in cleanup order.
        reason (str): Failure message assigned to each unfinished watcher.
    """
    for status in statuses:
        if not status.done:
            try:
                status.set_exception(RuntimeError(reason))
            except InvalidState:
                pass  # A monitor completion was already scheduled.
        status._cleanup()


def _cancel_statuses(statuses: Iterable[_StatusBase], error: Exception) -> StatusBase | None:
    """
    Release owned children and await sequences/composites which perform their own cleanup.
    """
    pending = []
    seen = set()

    def cancel(status):
        if id(status) in seen:
            return
        seen.add(id(status))
        if not status.done:
            try:
                status.set_exception(RuntimeError("Sequence operation interrupted"))
            except Exception as cleanup_error:  # noqa: BLE001 - release every child.
                if not isinstance(cleanup_error, InvalidState):
                    error.add_note(f"Cancelling sequence child failed: {cleanup_error!r}")
        if isinstance(status, SequenceStatus):
            # Sequences have no constructor timeout and acknowledge their owned
            # asynchronous cleanup before they can complete.
            pending.append(status)
            return
        cleanup = getattr(status, "_cleanup", None)
        if cleanup is not None:
            try:
                cleanup()
            except Exception as cleanup_error:  # noqa: BLE001 - continue cleanup.
                error.add_note(f"Releasing sequence child failed: {cleanup_error!r}")
        if isinstance(status, (AndStatus, _AndStatus)):
            # Native constructor timeouts can finish a composite without entering
            # its owned cleanup path. Traverse completed composites as well.
            cancel(status.left)
            cancel(status.right)

    for status in statuses:
        cancel(status)
    if not pending:
        return None
    settled = StatusBase(description="Nested status cleanup finished")
    remaining = set(pending)
    lock = threading.Lock()

    def completed(status):
        nested_error = status.exception(timeout=0)
        with lock:
            if nested_error is not error:
                for note in tuple(getattr(nested_error, "__notes__", ())):
                    error.add_note(f"Nested sequence cleanup: {note}")
            remaining.discard(status)
            last = not remaining
        if last:
            settled.set_finished()

    for status in pending:
        status.add_callback(completed)
    return settled


class SequenceStatus(StatusBase):
    """
    Run operations in order, waiting for each returned status before starting the next.

    Each step is a callable returning a status or None. None means the operation
    finished synchronously. Operations run in the caller or child callback thread;
    this class creates no worker and does not make blocking I/O asynchronous.
    Each operation inherits the context variables present at construction, including
    when a preceding status completes on another thread.

    The sequence owns the statuses returned by its steps. Failure or set_exception()
    prevents future steps, cancels owned subscriptions, and runs on_failure exactly
    once before reporting failure. An asynchronous cleanup status is awaited too.
    Cancellation during a synchronous step waits for that call to return, then cancels
    its result. Steps must still serialize hardware writes with stop themselves.

    Child timeouts apply normally. There is deliberately no sequence-wide timeout:
    it could report completion before the owned failure cleanup had finished.
    """

    def __init__(
        self,
        obj: Device | None = None,
        *,
        steps: Iterable[Callable[[], _StatusBase | None]],
        on_failure: Callable[[Exception], _StatusBase | None] | None = None,
        description: str | None = None,
        run: bool = True,
    ) -> None:
        """
        Create a sequence and optionally start its first operation immediately.

        Args:
            obj (Device | None): Device associated with status diagnostics.
            steps (Iterable[Callable[[], StatusBase | None]]): Operations to start in
                declaration order. Pass callables, not already-started status objects.
            on_failure (Callable[[Exception], StatusBase | None] | None): Cleanup receiving
                the original failure. Cleanup errors are attached as notes to that error.
            description (str | None): Human-readable status description.
            run (bool): Start immediately when True. Use False to register cancellation
                and store the sequence on its owner before calling run().
        """
        operations = tuple(steps)
        if any(not callable(step) for step in operations):
            raise TypeError("SequenceStatus steps must be callables")
        if on_failure is not None and not callable(on_failure):
            raise TypeError("on_failure must be callable")
        super().__init__(obj, description=description)
        self._sequence_lock = threading.RLock()
        self._steps = iter(operations)
        self._context = copy_context()
        self._on_failure = on_failure
        self._active_child: _StatusBase | None = None
        self._sequence_error: Exception | None = None
        self._started = False
        self._driving = False
        self._failing = False
        self._finalizing = False
        if run:
            self.run()

    def run(self) -> None:
        """
        Start once; calls after startup or completion are harmless.
        """
        with self._sequence_lock:
            if self._started or self._finalizing or self.done:
                return
            self._started = True
        self._drive()

    def set_exception(self, exc: Exception | type[Exception]) -> None:
        """
        Abort future operations and report failure only after owned cleanup finishes.

        Args:
            exc (Exception | type[Exception]): Original failure or cancellation reason.
                The first failure wins; subsequent cancellation requests are harmless.
        """
        if isinstance(exc, type) and issubclass(exc, Exception):
            exc = exc()
        if not isinstance(exc, Exception):
            raise TypeError(f"Expected an Exception, got {exc!r}")
        with self._sequence_lock:
            if self._finalizing or self.done or self._sequence_error is not None:
                return
            error = _status_failure(self._active_child)
            self._sequence_error = exc if error is None else error
        self._drive()

    def set_finished(self) -> None:
        """
        Reject external success: only finishing every step can succeed a sequence.
        """
        raise RuntimeError("SequenceStatus succeeds only after all of its steps finish")

    def _cleanup(self) -> None:
        self.set_exception(RuntimeError("Sequence no longer needed by its parent"))

    def _child_done(self, _status: _StatusBase) -> None:
        self._drive()

    def _record_failure(self, error: Exception) -> None:
        with self._sequence_lock:
            if self._sequence_error is None:
                self._sequence_error = error
            elif error is not self._sequence_error:
                self._sequence_error.add_note(f"Sequence cleanup also failed: {error!r}")

    def _cancel_owned(self, child: _StatusBase | None, error: Exception) -> _StatusBase | None:
        """Release owned subscriptions and await nested sequence cleanup, if needed."""
        return None if child is None else _cancel_statuses((child,), error)

    def _drive(self) -> None:
        """Trampoline completed steps without recursion or holding locks during I/O."""
        with self._sequence_lock:
            if self._driving or self._finalizing or self.done:
                return
            self._driving = True
        while True:
            with self._sequence_lock:
                if self._sequence_error is not None and not self._failing:
                    child, error, cleanup = (
                        self._active_child,
                        self._sequence_error,
                        self._on_failure,
                    )
                    self._active_child = None
                    self._on_failure = None
                    self._failing = True
                    self._steps = iter(
                        (
                            lambda child=child, error=error: self._cancel_owned(child, error),
                            lambda cleanup=cleanup, error=error: (
                                cleanup(error) if cleanup is not None else None
                            ),
                        )
                    )
                child = self._active_child
                if child is not None and not child.done:
                    # Release drive ownership atomically with checking pending work.
                    # Completion callbacks can then acquire it without losing a wakeup.
                    self._driving = False
                    return
                if child is None:
                    try:
                        step = next(self._steps)
                    except StopIteration:
                        self._finalizing = True
                        self._driving = False
                        self._steps = iter(())
                        self._on_failure = None
                        error = self._sequence_error
                        break
            if child is not None:
                try:
                    child.wait(timeout=0)
                except Exception as error:  # noqa: BLE001 - forward child/cleanup failure.
                    self._record_failure(error)
                    with self._sequence_lock:
                        if self._failing:
                            self._active_child = None
                            # A failed cleanup composite can still own a nested
                            # sequence whose asynchronous cleanup has not finished.
                            # Release and await that work before reporting failure.
                            original = self._sequence_error
                            assert original is not None
                            self._steps = chain(
                                (
                                    lambda child=child, error=original: self._cancel_owned(
                                        child, error
                                    ),
                                ),
                                self._steps,
                            )
                else:
                    with self._sequence_lock:
                        self._active_child = None
                continue
            try:
                result = self._context.copy().run(step)
                if result is not None and not isinstance(result, _StatusBase):
                    raise TypeError("SequenceStatus steps must return a status or None")
                with self._sequence_lock:
                    self._active_child = result
                if result is not None:
                    result.add_callback(self._child_done)
            except Exception as error:  # noqa: BLE001 - keep cleanup on the same path.
                self._record_failure(error)
        if error is None:
            super().set_finished()
        else:
            super().set_exception(error)


class Status(_Status):
    """Thin wrapper around StatusBase to add __and__ operator."""

    def __init__(
        self,
        obj=None,
        timeout=None,
        settle_time=0,
        done=None,
        success=None,
        description: str | None = None,
    ):
        self._timeout_diagnostics = _StatusTimeoutDiagnostics(description=description)
        super().__init__(
            obj=obj, timeout=timeout, settle_time=settle_time, done=done, success=success
        )
        self._timeout_diagnostics.bind(self)

    def __and__(self, other):
        """Returns a new 'composite' status object, AndStatus"""
        return AndStatus(self, other)

    def _run_callbacks(self):
        _run_callbacks_with_diagnostics(self, self._timeout_diagnostics)


class DeviceStatus(_DeviceStatus):
    """Thin wrapper around DeviceStatus to add __and__ operator."""

    def __init__(self, device, description: str | None = None, **kwargs):
        self._timeout_diagnostics = _StatusTimeoutDiagnostics(description=description)
        super().__init__(device=device, **kwargs)
        self._timeout_diagnostics.bind(self)

    def __and__(self, other):
        """Returns a new 'composite' status object, AndStatus"""
        return AndStatus(self, other)

    def _run_callbacks(self):
        _run_callbacks_with_diagnostics(self, self._timeout_diagnostics)


class MoveStatus(_MoveStatus):
    """Thin wrapper around MoveStatus to ensure __and__ operator and stop on failure."""

    def __init__(
        self, positioner, target, *, start_ts=None, description: str | None = None, **kwargs
    ):
        self._timeout_diagnostics = _StatusTimeoutDiagnostics(description=description)
        super().__init__(positioner=positioner, target=target, start_ts=start_ts, **kwargs)
        self._timeout_diagnostics.bind(self)

    def __and__(self, other):
        """Returns a new 'composite' status object, AndStatus"""
        return AndStatus(self, other)

    def _run_callbacks(self):
        _run_callbacks_with_diagnostics(self, self._timeout_diagnostics)


class SubscriptionStatus(StatusBase):
    """Subscription status implementation based on wrapped StatusBase implementation."""

    def __init__(
        self,
        obj: Device | Signal,
        callback: Callable,
        event_type=None,
        timeout=None,
        settle_time=None,
        run=True,
        description: str | None = None,
    ):
        # Store device and attribute information
        self.callback = callback
        self.obj = obj
        self._cleanup_requested = False
        # Start timeout thread in the background
        super().__init__(obj=obj, timeout=timeout, settle_time=settle_time, description=description)
        try:
            self.obj.subscribe(self.check_value, event_type=event_type, run=run)
        except Exception as error:
            try:
                self._cleanup()
            except Exception as cleanup_error:  # noqa: BLE001 - preserve setup failure.
                error.add_note(f"Subscription cleanup also failed: {cleanup_error!r}")
            try:
                self.set_exception(error)
            except InvalidState:
                pass  # Timeout already committed its terminal failure.
            raise
        else:
            # Timeout cleanup may have run before subscribe registered anything.
            if self._cleanup_requested:
                self.obj.clear_sub(self.check_value)

    def check_value(self, *args, **kwargs):
        """Update the status object"""
        if self._cleanup_requested:
            return
        try:
            success = self.callback(*args, **kwargs)
        except Exception as e:
            _log_callback_exception(self, e)
            self.set_exception(e)
            return
        if success:
            self.set_finished()

    def set_finished(self):
        """Mark as finished successfully."""
        self._cleanup()
        super().set_finished()

    def _handle_failure(self):
        """Clear subscription on failure, run callbacks through super()"""
        self._cleanup()
        return super()._handle_failure()

    def _cleanup(self) -> None:
        self._cleanup_requested = True
        self.obj.clear_sub(self.check_value)


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
        signal: Signal,
        value: float | int | str,
        *,
        operation_success: Literal["==", "!=", "<", "<=", ">", ">="] = "==",
        failure_value: float | int | str | list[float | int | str] | None = None,
        operation_failure: Literal["==", "!=", "<", "<=", ">", ">="] = "==",
        timeout: float = None,
        settle_time: float = 0,
        run: bool = True,
        event_type=None,
        description: str | None = None,
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
            description=description,
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
            _log_callback_exception(self, e)
            self.set_exception(e)
            return False


class ExceptionStatus(CompareStatus):
    """
    Status to watch for an error condition on a signal without blocking composite success.

    The status remains pending while the monitored value is in its expected state. If the
    comparison matches, the status fails immediately and any composite AndStatus containing
    it will fail as well. Unlike CompareStatus, this status never completes successfully on
    its own and is intended to be combined with primary statuses using ``&``.
    """

    _blocks_success = False

    def __init__(
        self,
        signal: Signal,
        value: float | int | str,
        *,
        operation: Literal["==", "!=", "<", "<=", ">", ">="] = "==",
        timeout: float = None,
        settle_time: float = 0,
        run: bool = True,
        event_type=None,
        exception: Exception | None = None,
        description: str | None = None,
    ):
        self._configured_exception = exception
        super().__init__(
            signal=signal,
            value=value,
            operation_success=operation,
            timeout=timeout,
            settle_time=settle_time,
            run=run,
            event_type=event_type,
            description=description,
        )

    def _compare_callback(self, value: any, **kwargs) -> bool:
        try:
            if isinstance(value, list):
                raise ValueError(f"List values are not supported. Received value: {value}")
            if self.op_map[self._operation_success](value, self._value):
                if self._configured_exception is not None:
                    raise self._configured_exception
                raise ValueError(
                    f"ExceptionStatus for signal {self._signal.name} reached monitored value "
                    f"{self._operation_success} {self._value}. Current value: {value}"
                )
            return False
        except Exception as e:
            _log_callback_exception(self, e)
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
        signal: Signal,
        transitions: list[float | int | str],
        *,
        strict: bool = True,
        failure_states: list[float | int | str] | None = None,
        run: bool = True,
        timeout: float = None,
        settle_time: float = 0,
        event_type=None,
        description: str | None = None,
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
            description=description,
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
            _log_callback_exception(self, e)
            self.set_exception(e)
            return False


def destroy_subdevices(device: Device) -> None:
    """
    Destroy instantiated children without pre-empting custom owner cleanup.

    Plain Ophyd Device.destroy disconnects descendant signals without invoking child
    device destructors. For an ordinary grouping Device with no destroy override,
    traverse its children first. Invoke a custom destructor before its descendants,
    so the owner can stop workers or flush data while child resources remain usable.

    Custom grouping destructors must call this helper after their own cleanup and
    before super().destroy() when child cleanup needs connected signals::

        def destroy(self):
            self.flush_owned_resources()
            destroy_subdevices(self)
            super().destroy()

    PSIDeviceBase already provides this ordering through on_destroy. After a custom
    destructor returns or fails, traverse remaining descendants as best-effort cleanup;
    this cannot reconnect signals an uncooperative destructor already disconnected.
    Only instantiated components are visited, including descendants of groups already
    marked destroyed. Continue after cleanup failures and report the first error with
    subsequent failures attached as notes. DeviceCleanupBlockedError is a safety barrier:
    leave that subtree's signals connected and propagate it before native destruction.
    Custom owners must also respect this barrier rather than destroying in a finally.

    Args:
        device (Device): Parent whose instantiated child devices should be destroyed.

    Raises:
        Exception: A descendant cleanup fails, after remaining cleanups are attempted.
    """
    from ophyd import Device

    errors = []
    for child in tuple(device._signals.values()):
        if not isinstance(child, Device):
            continue
        ordinary_group = type(child).destroy is Device.destroy
        if ordinary_group:
            try:
                destroy_subdevices(child)
            except DeviceCleanupBlockedError as error:
                errors.append(error)
                continue  # Its descendants still need this group's connected signals.
            except Exception as error:  # noqa: BLE001 - still destroy this group and siblings.
                errors.append(error)
        if not child._destroyed:
            try:
                child.destroy()
            except DeviceCleanupBlockedError as error:
                errors.append(error)
                continue  # Do not bypass the owner's refusal to release live resources.
            except Exception as error:  # noqa: BLE001 - finish all child cleanup.
                errors.append(error)
        if not ordinary_group:
            try:
                destroy_subdevices(child)
            except Exception as error:  # noqa: BLE001 - recover children a custom owner missed.
                errors.append(error)
    if errors:
        primary = next((e for e in errors if isinstance(e, DeviceCleanupBlockedError)), errors[0])
        for error in errors:
            if error is not primary:
                primary.add_note(f"Additional child cleanup failure: {error!r}")
        raise primary


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


class DeviceCleanupBlockedError(RuntimeError):
    """
    Device resources are still in use; destruction must wait and may be retried.
    """


class TaskShutdownError(DeviceCleanupBlockedError):
    """
    Task workers still own resources; destruction must wait and may be retried.
    """


class TaskStatus(StatusBase):
    """Thin wrapper around StatusBase to add information about tasks"""

    def __init__(
        self,
        obj: Device | Signal,
        *,
        timeout=None,
        settle_time=0,
        done=None,
        success=None,
        description: str | None = None,
    ):
        super().__init__(
            obj=obj,
            timeout=timeout,
            settle_time=settle_time,
            done=done,
            success=success,
            description=description,
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
        self._shutdown_requests = 0
        self._cancelled_tasks: set[str] = set()
        self._executing_tasks: set[str] = set()

    def _check_accepting_tasks(self) -> None:
        """
        Reject setup during shutdown, while cancelled workers drain, or after destruction.
        """
        if (
            self._shutdown_requests
            or self._cancelled_tasks
            or getattr(self._parent, "_destroying", False)
            or getattr(self._parent, "_destroyed", False)
        ):
            raise TaskShutdownError("Task handler is shutting down; retry after workers exit")

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
        with self._lock:
            self._check_accepting_tasks()
            self._tasks[task_status.task_id] = (task_status, thread)
            if run is True:
                self.start_task(task_status)
        return task_status

    def start_task(self, task_status: TaskStatus) -> None:
        """Start a task,

        Args:
            task_status: The task status object.
        """
        with self._lock:
            self._check_accepting_tasks()
            if task_status.task_id not in self._tasks:
                raise TaskShutdownError("Task was cancelled or has already completed")
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
            try:
                with self._lock:
                    if task_status.task_id in self._cancelled_tasks:
                        raise TaskKilledError("Task cancelled before execution")
                    self._executing_tasks.add(task_status.task_id)
                task(*task_args, **task_kwargs)
            finally:
                # Never inject cancellation into status callbacks or final bookkeeping.
                with self._lock:
                    self._executing_tasks.discard(task_status.task_id)
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
            if task_status.task_id in self._cancelled_tasks:
                task_status.state = TaskState.KILLED
                task_status.set_exception(TaskKilledError("Task cancelled before completion"))
            else:
                task_status.state = TaskState.COMPLETED
                task_status.set_finished()
        finally:
            with self._lock:
                self._executing_tasks.discard(task_status.task_id)
                self._tasks.pop(task_status.task_id, None)
                self._cancelled_tasks.discard(task_status.task_id)

    def kill_task(self, task_status: TaskStatus) -> None:
        """
        Cancel a task, including deferred work with no running thread.

        Args:
            task_status (TaskStatus): Registered task to cancel. Repeated calls are
                harmless. Deferred cancellation completes synchronously; running
                workers are interrupted once and must be joined by shutdown().
        """
        deferred = False
        with self._lock:
            task = self._tasks.get(task_status.task_id)
            if task is None or task_status.task_id in self._cancelled_tasks:
                return
            self._cancelled_tasks.add(task_status.task_id)
            thread = task[1]
            if thread.ident is None:
                self._tasks.pop(task_status.task_id, None)
                self._cancelled_tasks.discard(task_status.task_id)
                deferred = True
            elif (
                task_status.task_id not in self._executing_tasks
                or thread is threading.current_thread()
            ):
                return
            if not deferred:
                ident = ctypes.c_long(thread.ident)
                exc = ctypes.py_object(TaskKilledError)
                try:
                    res = set_async_exc(ident, exc)
                    if res == 0:
                        raise ValueError("Invalid thread ID")
                    if res > 1:
                        set_async_exc(ident, None)
                        logger.warning(
                            f"Exception while killing thread {ident}; return value: {res}"
                        )
                except Exception as error:  # pylint: disable=broad-except
                    logger.warning(f"Exception while killing thread {ident}: {error}")
        if deferred:
            task_status.state = TaskState.KILLED
            try:
                task_status.set_exception(TaskKilledError("Task cancelled before startup"))
            except InvalidState:
                pass  # Another caller already completed this deferred task.

    def shutdown(self, *, timeout: float = 2) -> None:
        """
        Cancel pending work and wait for every started worker to exit.

        Cancellation of blocking native I/O is best effort. If workers cannot exit
        within the shared deadline, raise TaskShutdownError and keep their resources
        alive. Calling from an owned worker also raises rather than joining itself
        or claiming that its resources can already be destroyed. New submissions
        are rejected until cancelled workers have exited; a later scan may then reuse
        the handler unless device destruction has begun.

        Args:
            timeout (float): Finite positive maximum wait in seconds. Defaults to 2.

        Raises:
            TaskShutdownError: An owned worker calls shutdown or workers remain alive.
            ValueError: timeout is not finite and positive.
        """
        if not 0 < timeout < float("inf"):
            raise ValueError("Task shutdown timeout must be finite and positive")
        deadline = monotonic() + timeout
        with self._lock:
            self._shutdown_requests += 1
            tasks = tuple(self._tasks.values())
        try:
            for status, _thread in tasks:
                self.kill_task(status)
            for status, thread in tasks:
                if thread.ident is None:
                    status.state = TaskState.KILLED
                    if not status.done:
                        try:
                            status.set_exception(TaskKilledError("Task cancelled before startup"))
                        except InvalidState:
                            pass  # Another shutdown caller already cancelled this task.
                    with self._lock:
                        self._tasks.pop(status.task_id, None)
                        self._cancelled_tasks.discard(status.task_id)
            if any(thread is threading.current_thread() for _, thread in tasks):
                raise TaskShutdownError("A task worker cannot finish its own shutdown")
            for _status, thread in tasks:
                if thread.ident is not None:
                    thread.join(timeout=max(0, deadline - monotonic()))
            alive = [thread.name for _, thread in tasks if thread.is_alive()]
            if alive:
                raise TaskShutdownError(f"Task workers did not stop before timeout: {alive}")
        finally:
            with self._lock:
                self._shutdown_requests -= 1


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
