"""Track and cooperatively cancel Ophyd Signal.set workers by device root.

The in-place patch also covers existing Signal aliases and subclasses that
delegate to Signal.set. Custom _set_and_wait hooks are called unchanged; they
can only observe cancellation after returning unless they delegate to the base
hook. EPICS put-completion sets and independent set overrides are not patched.

Public usage, with an Ophyd root device::

    from ophyd_devices import set_registry

    operations = set_registry.active(root)
    grouped = set_registry.by_root()
    set_registry.cancel(root)

A captured operation can also be cancelled individually with
``operation.cancel()``. Cancellation requests are asynchronous: the worker must
release the signal before another set can start. Normally this happens before
the returned status finishes; an externally completed status alone does not
establish that its worker has finished.

Device stop scopes also reject new sets from other threads until the hardware
stop finishes. The stop thread may run synchronous cleanup sets. Cancelling an
individual operation or calling ``set_registry.cancel`` does not open a stop
scope, so completion callbacks can start subsequent operations in those cases.
"""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Generator, Iterable
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from functools import wraps
from types import SimpleNamespace
from typing import Any

import numpy as np
from ophyd import Signal
from ophyd.ophydobj import OphydObject
from ophyd.status import Status
from ophyd.utils.epics_pvs import _compare_maybe_enum
from ophyd.utils.errors import DestroyedError, InvalidState, StatusTimeoutError, WaitTimeoutError

# The compatibility patch and cooperating registry helpers intentionally access
# Ophyd's worker hooks and their own internal operation state.
# pylint: disable=protected-access


_signal_set_patch_state = globals().get("_signal_set_patch_state")
if _signal_set_patch_state is None:

    class SetCancelledError(Exception):
        """A pending Signal.set operation was deliberately cancelled."""

    @dataclass(eq=False)
    class SetOperation:
        """One active set request, retained until its worker releases the signal."""

        signal: Signal
        value: Any
        status: Status
        started_at: float = field(default_factory=time.monotonic)
        _root: OphydObject = field(init=False, repr=False)
        _cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

        def __post_init__(self) -> None:
            self._root = self.signal.root

        @property
        def cancel_requested(self) -> bool:
            """Whether cancellation was requested for this particular operation."""
            return self._cancel_event.is_set()

        def cancel(self) -> None:
            """Request cancellation without affecting subsequent sets on the signal."""
            with set_registry._lock:
                self._cancel_event.set()

        def _check_cancelled(self) -> None:
            if self.cancel_requested:
                raise SetCancelledError(f"Set operation for {self.signal.name} was cancelled")

    class SetRegistry:
        """Thread-safe snapshots of active base Signal.set operations."""

        def __init__(self) -> None:
            self._lock = threading.RLock()
            self._operations: dict[int, SetOperation] = {}
            self._stop_context = threading.local()
            self._stopping_roots: dict[int, set[int]] = {}

        def active(self, root: OphydObject | None = None) -> tuple[SetOperation, ...]:
            """Return active operations, optionally matching the exact root object."""
            with self._lock:
                return tuple(
                    operation
                    for operation in self._operations.values()
                    if root is None or operation._root is root
                )

        def by_root(self) -> dict[OphydObject, tuple[SetOperation, ...]]:
            """Return a snapshot grouped by the Ophyd root objects."""
            with self._lock:
                grouped: dict[OphydObject, list[SetOperation]] = {}
                for operation in self._operations.values():
                    grouped.setdefault(operation._root, []).append(operation)
                return {root: tuple(operations) for root, operations in grouped.items()}

        def cancel(self, root: OphydObject) -> tuple[SetOperation, ...]:
            """Request cancellation of the operations currently active for a root."""
            with self._lock:
                operations = self.active(root)
                for operation in operations:
                    operation.cancel()
                return operations

        @contextmanager
        def stopping(
            self, root: OphydObject, operations: tuple[SetOperation, ...] | None = None
        ) -> Generator[tuple[SetOperation, ...], None, None]:
            """Reuse one root snapshot across nested synchronous device stop calls.

            A caller may supply an earlier snapshot, including an empty tuple.
            Only the outermost scope requests cancellation, before stop hooks run.
            Synchronous cleanup sets from the sole stop thread are not included.
            Other threads, including completion callbacks, receive RuntimeError
            for new sets and must retry after the stop scope finishes.
            """
            scopes = getattr(self._stop_context, "scopes", None)
            if scopes is None:
                scopes = self._stop_context.scopes = {}
            root_key = id(root)
            if root_key in scopes:
                yield scopes[root_key]
                return
            # Capture and cancel together so an old worker cannot finish and be
            # replaced between the snapshot and its cancellation request.
            with self._lock:
                captured = self.active(root) if operations is None else operations
                scopes[root_key] = captured
                owner = threading.get_ident()
                self._stopping_roots.setdefault(root_key, set()).add(owner)
                for operation in captured:
                    operation.cancel()
            try:
                # Hardware hooks and status callbacks must not hold our lock.
                yield captured
            finally:
                with self._lock:
                    del scopes[root_key]
                    owners = self._stopping_roots[root_key]
                    owners.remove(owner)
                    if not owners:
                        del self._stopping_roots[root_key]

        @contextmanager
        def stopping_many(self, roots: Iterable[OphydObject]) -> Generator[None, None, None]:
            """Reserve all roots before cancelled workers can start callback sets.

            Snapshots and admission gates are installed under one lock. Device
            stop hooks run after it is released, with the same nested-scope and
            synchronous cleanup behavior as :meth:`stopping`.
            """
            with ExitStack() as stack:
                with self._lock:
                    for root in roots:
                        stack.enter_context(self.stopping(root))
                yield


# importlib.reload reuses this module's globals. Keep state and public types
# stable so aliases, running workers and their cancellation handles still work;
# in particular, never capture our own wrappers as Ophyd's original methods.
if _signal_set_patch_state is None:
    _signal_set_patch_state = SimpleNamespace(
        registry=SetRegistry(),
        worker_context=threading.local(),
        original_set=Signal.set,
        original_set_and_wait=Signal._set_and_wait,
        cancelled_error=SetCancelledError,
        operation_type=SetOperation,
        registry_type=SetRegistry,
    )
set_registry = _signal_set_patch_state.registry
_worker_context = _signal_set_patch_state.worker_context
_original_set = _signal_set_patch_state.original_set
_original_set_and_wait = _signal_set_patch_state.original_set_and_wait
SetCancelledError = _signal_set_patch_state.cancelled_error
SetOperation = _signal_set_patch_state.operation_type
SetRegistry = _signal_set_patch_state.registry_type


def _release_exception_tracebacks(error: BaseException) -> None:
    """Keep error/cause diagnostics without retaining completed worker frames."""
    pending = [error]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        current.__traceback__ = None
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)


def _wait_for_value(  # pylint: disable=too-many-arguments
    operation: SetOperation,
    value: Any,
    *,
    timeout: float | None,
    poll_time: float = 0.01,
    atol: float | None = None,
    rtol: float | None = None,
) -> None:
    """Preserve Ophyd comparison semantics while making its polling interruptible."""
    signal = operation.signal
    expiration_time = time.monotonic() + timeout if timeout is not None else None
    get_kwargs = {}
    if isinstance(value, (list, np.ndarray, tuple)):
        get_kwargs["count"] = len(value)
    current_value = signal.get(**get_kwargs)
    if atol is None:
        atol = signal.tolerance
    if rtol is None:
        rtol = signal.rtolerance
    enum_strings = getattr(signal, "enum_strs", ())
    while (value is not None and current_value is None) or not _compare_maybe_enum(
        value, current_value, enum_strings, atol, rtol
    ):
        operation._check_cancelled()
        if poll_time < 0:
            raise ValueError("sleep length must be non-negative")
        operation._cancel_event.wait(poll_time)
        operation._check_cancelled()
        if poll_time < 0.1:
            poll_time *= 2
        current_value = signal.get(**get_kwargs)
        if expiration_time is not None and time.monotonic() > expiration_time:
            raise TimeoutError(
                f"Attempted to set {signal!r} to value {value!r} and timed out "
                f"after {timeout!r} seconds. Current value is {current_value!r}."
            )
    operation._check_cancelled()


def _put_and_wait(  # pylint: disable=too-many-arguments
    operation: SetOperation,
    value: Any,
    *,
    timeout: float | None,
    poll_time: float = 0.01,
    atol: float | None = None,
    rtol: float | None = None,
    **kwargs: Any,
) -> None:
    operation._check_cancelled()
    operation.signal.put(value, **kwargs)
    operation._check_cancelled()
    return _wait_for_value(
        operation, value, timeout=timeout, poll_time=poll_time, atol=atol, rtol=rtol
    )


@wraps(_original_set_and_wait)
def _cancellable_set_and_wait(
    self: Signal, value: Any, timeout: float | None, **kwargs: Any
) -> None:
    operation = getattr(_worker_context, "operation", None)
    if operation is None or operation.signal is not self:
        return _original_set_and_wait(self, value, timeout, **kwargs)
    return _put_and_wait(
        operation, value, timeout=timeout, atol=self.tolerance, rtol=self.rtolerance, **kwargs
    )


def _run_set(
    operation: SetOperation,
    timeout: float | None,
    settle_time: float | None,
    kwargs: dict[str, Any],
) -> None:
    signal = operation.signal
    error = RuntimeError(f"Set worker for {signal.name} terminated unexpectedly")
    _worker_context.operation = operation
    try:
        operation._check_cancelled()
        signal._set_and_wait(operation.value, timeout, **kwargs)
        operation._check_cancelled()
        if settle_time is not None:
            if settle_time < 0:
                raise ValueError("sleep length must be non-negative")
            operation._cancel_event.wait(settle_time)
        operation._check_cancelled()
        error = None
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Every driver error at this worker boundary must resolve the status.
        error = exc
        if isinstance(exc, TimeoutError):
            signal.log.warning("set(value=%r) failed: %s", operation.value, str(exc))
        elif not isinstance(exc, SetCancelledError):
            # Formatting now preserves the full diagnostic stack without giving
            # buffered log handlers a live traceback that retains driver locals.
            signal.log.error("set(value=%r) failed:\n%s", operation.value, traceback.format_exc())
    finally:
        del _worker_context.operation
        with set_registry._lock:
            if operation.cancel_requested:
                error = SetCancelledError(f"Set operation for {signal.name} was cancelled")
            if set_registry._operations.get(id(signal)) is operation:
                del set_registry._operations[id(signal)]
                signal._set_thread = None
        # Clearing ownership first allows completion callbacks to call set().
        # Callbacks must never run while the registry lock is held.
        try:
            if error is None:
                operation.status.set_finished()
            else:
                if isinstance(error, (StatusTimeoutError, WaitTimeoutError)):
                    # Ophyd reserves these exceptions for its own status logic.
                    # A nested hook's status.wait() can nevertheless raise them.
                    original_error = error
                    error = TimeoutError(str(original_error))
                    error.__cause__ = original_error
                # Signal._status outlives this worker. Retaining traceback frames
                # here would also retain arbitrary driver buffers and arguments.
                _release_exception_tracebacks(error)
                operation.status.set_exception(error)
        except InvalidState:
            # Drivers may already have completed this status in cancel_on_stop.
            pass


@wraps(_original_set)
def _cancellable_set(
    self: Signal,
    value: Any,
    *,
    timeout: float | None = None,
    settle_time: float | None = None,
    **kwargs: Any,
) -> Status:
    with set_registry._lock:
        root = self.root
        if self._destroyed or getattr(root, "_destroyed", False):
            raise DestroyedError(
                f"Cannot set {self.name}: signal or device root has been destroyed"
            )
        stop_owners = set_registry._stopping_roots.get(id(root))
        if stop_owners and stop_owners != {threading.get_ident()}:
            raise RuntimeError(f"Cannot set {self.name} while device root {root.name} is stopping")
        if self._set_thread is not None or id(self) in set_registry._operations:
            raise RuntimeError(f"Another set() call is still in progress for {self.name}")
        status = Status(self)
        operation = SetOperation(self, value, status)
        thread = self.cl.thread_class(
            target=_run_set, args=(operation, timeout, settle_time, kwargs)
        )
        thread.daemon = True
        self._status = status
        self._set_thread = thread
        set_registry._operations[id(self)] = operation
        try:
            thread.start()
        except BaseException:
            del set_registry._operations[id(self)]
            self._set_thread = None
            raise
    return status


def install_signal_set_patch() -> None:
    """Install the idempotent in-place Signal patch in the current process."""
    with set_registry._lock:
        if Signal.set is _cancellable_set:
            return
        Signal.set = _cancellable_set
        Signal._set_and_wait = _cancellable_set_and_wait
