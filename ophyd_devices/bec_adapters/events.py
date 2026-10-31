"""Ordered, owned delivery of native-independent device events."""

from __future__ import annotations

import threading
import weakref
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field

from bec_lib.device_backend import DeviceEvent, EventContext
from bec_lib.logger import bec_logger


class EventDeliveryError(RuntimeError):
    """Publication failed; distinct from native resource disposal failing."""


@dataclass(frozen=True, slots=True)
class _DeliveryFailure:
    error_type: str
    message: str

    def exception(self) -> EventDeliveryError:
        """Build a detached diagnostic without retaining the producer traceback."""
        return EventDeliveryError(f"{self.error_type}: {self.message}")


@dataclass(slots=True)
class _FailureWindow:
    """Two compact representatives for failures since the acknowledged frontier."""

    first: tuple[int, _DeliveryFailure] | None = None
    last: tuple[int, _DeliveryFailure] | None = None

    def add(self, sequence: int, failure: _DeliveryFailure) -> None:
        """Retain representative failures at this window's two boundaries."""
        if self.first is None or sequence < self.first[0]:
            self.first = sequence, failure
        if self.last is None or sequence > self.last[0]:
            self.last = sequence, failure

    def acknowledge(self, sequence: int) -> None:
        """Discard reported evidence while retaining a later representative."""
        if self.last is None or self.last[0] <= sequence:
            self.first = self.last = None
        elif self.first is not None and self.first[0] <= sequence:
            self.first = self.last


@dataclass(eq=False, slots=True, weakref_slot=True)
class _EventFence:
    sequence: int
    errors: _FailureWindow = field(default_factory=_FailureWindow)


class EventSubscription:
    """Drain accepted events before disposal; native callbacks only enqueue."""

    def __init__(
        self,
        executor: ThreadPoolExecutor,
        callback: Callable[[DeviceEvent], None],
        *,
        context: Callable[[], EventContext] | None = None,
        delivery_scope: Callable[[frozenset[str]], AbstractContextManager] | None = None,
    ) -> None:
        self._executor = executor
        self._callback = callback
        self.context = context
        self._delivery_scope = delivery_scope
        self._condition = threading.Condition()
        self._lifecycle = threading.RLock()
        self.registration = "all"
        self._accepting = True
        self._disposed = False
        self._pending = 0
        self._accepted = 0
        self._delivered = 0
        self._completed: set[int] = set()
        self._active_thread: int | None = None
        self.on_close: Callable[[], None] | None = None
        # Keep fixed-size summaries, never traceback/payload graphs or per-event
        # failure history. Each live receipt fence owns its own bounded window.
        self._errors: list[_DeliveryFailure] = []
        self._failure_count = 0
        self._failures = _FailureWindow()
        self._fences: weakref.WeakSet[_EventFence] = weakref.WeakSet()
        self._unsubscribers: list[Callable[[], None]] = []

    def own(self, unsubscribe: Callable[[], None]) -> None:
        """Register removal of a native callback owned by this subscription."""
        with self._condition:
            if self._accepting:
                self._unsubscribers.append(unsubscribe)
                return
        try:
            unsubscribe()
        except Exception:
            with self._condition:
                self._unsubscribers.append(unsubscribe)
            raise
        raise RuntimeError("Subscription disposal has already started")

    def emit(self, event: DeviceEvent, *, ancestry: frozenset[str] = frozenset()) -> None:
        """Accept a native event without executing service work on its caller."""
        with self._condition:
            if not self._accepting:
                return
            self._pending += 1
            self._accepted += 1
            sequence = self._accepted
            try:
                self._executor.submit(self._deliver, sequence, event, ancestry)
            except Exception:
                self._pending -= 1
                self._accepted -= 1
                self._condition.notify_all()
                raise

    def _deliver(self, sequence: int, event: DeviceEvent, ancestry: frozenset[str]) -> None:
        with self._condition:
            self._active_thread = threading.get_ident()
        try:
            scope = self._delivery_scope(ancestry) if self._delivery_scope else nullcontext()
            with scope:
                self._callback(event)
        except Exception as error:
            failure = _DeliveryFailure(type(error).__name__, str(error)[:2048])
            with self._condition:
                self._failure_count += 1
                if not self._errors:
                    self._errors.append(failure)
                self._failures.add(sequence, failure)
                for fence in self._fences:
                    if sequence <= fence.sequence:
                        fence.errors.add(sequence, failure)
            bec_logger.logger.error(
                f"Device event delivery failed for {event.source.qualified_name} "
                f"({event.channel or event.kind}): {failure.error_type}: {failure.message}"
            )
        finally:
            with self._condition:
                self._active_thread = None
                self._pending -= 1
                self._completed.add(sequence)
                while self._delivered + 1 in self._completed:
                    self._delivered += 1
                    self._completed.remove(self._delivered)
                self._condition.notify_all()

    def fence(self) -> _EventFence:
        """Snapshot accepted work and own bounded failure evidence through it.

        Native delivery updates live fences directly. This avoids keeping one
        error record per event when an idle monitored device has no completions.
        """
        with self._condition:
            fence = _EventFence(
                self._accepted, _FailureWindow(self._failures.first, self._failures.last)
            )
            self._fences.add(fence)
            return fence

    def wait_for_fence(self, fence: _EventFence, timeout: float) -> None:
        """Wait only for a captured receipt frontier, not future arrivals."""
        with self._condition:
            if not self._condition.wait_for(lambda: self._delivered >= fence.sequence, timeout):
                raise TimeoutError("Timed out draining accepted device events")

    def take_delivery_errors(self, fence: _EventFence | None = None) -> list[BaseException]:
        """Acknowledge failures through a completed frontier, retaining later errors."""
        with self._condition:
            sequence = self._delivered if fence is None else fence.sequence
            if sequence > self._delivered:
                raise RuntimeError("Cannot acknowledge device events before their delivery")
            window = self._failures if fence is None else fence.errors
            failure = window.first
            if failure is not None and failure[0] > sequence:
                failure = None
            self._failures.acknowledge(sequence)
            for active in self._fences:
                active.errors.acknowledge(sequence)
            return [] if failure is None else [failure[1].exception()]

    def close(self) -> None:
        """Remove producers, then drain accepted events with a bounded wait."""
        self._drain(dispose=True)

    def suspend(self) -> None:
        """Drain before native destruction without invalidating the owner's token."""
        self._drain(dispose=False)

    def resume(self, register: Callable[[], None]) -> None:
        """Restore this token after failed destruction, unless its owner disposed it."""
        with self._lifecycle, self._condition:
            if self._disposed:
                return
            if self._unsubscribers:
                raise RuntimeError("Cannot restore until native subscription cleanup succeeds")
            self._accepting = True
            register()

    def _drain(self, *, dispose: bool) -> None:
        if (
            threading.current_thread().name.startswith("BECDeviceEvents")
            or self._active_thread == threading.get_ident()
        ):
            raise RuntimeError("A subscription cannot close itself from its delivery callback")
        with self._lifecycle:
            self._drain_owned(dispose=dispose)

    def _drain_owned(self, *, dispose: bool) -> None:
        with self._condition:
            self._accepting = False
            self._disposed |= dispose
            unsubscribers, self._unsubscribers = self._unsubscribers, []
        errors = []
        for unsubscribe in unsubscribers:
            try:
                unsubscribe()
            except Exception as error:
                errors.append(error)
                with self._condition:
                    self._unsubscribers.append(unsubscribe)
        with self._condition:
            if not self._condition.wait_for(lambda: self._pending == 0, timeout=10):
                raise TimeoutError("Timed out draining accepted device events")
        if dispose and not errors and self.on_close is not None:
            on_close, self.on_close = self.on_close, None
            on_close()
        if errors:
            raise errors[0]
        if self._errors:
            raise self._errors[0].exception()
