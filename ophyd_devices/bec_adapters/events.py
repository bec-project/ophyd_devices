"""Ordered, owned delivery of native-independent device events."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from bec_lib.device_backend import DeviceEvent
from bec_lib.logger import bec_logger


class EventSubscription:
    """Drain accepted events before disposal; native callbacks only enqueue."""

    def __init__(
        self, executor: ThreadPoolExecutor, callback: Callable[[DeviceEvent], None]
    ) -> None:
        self._executor = executor
        self._callback = callback
        self._condition = threading.Condition()
        self._lifecycle = threading.RLock()
        self.registration = "all"
        self._accepting = True
        self._disposed = False
        self._pending = 0
        self._active_thread: int | None = None
        self.on_close: Callable[[], None] | None = None
        self._errors: list[BaseException] = []
        self._unsubscribers: list[Callable[[], None]] = []

    def own(self, unsubscribe: Callable[[], None]) -> None:
        """Register removal of a native callback owned by this subscription."""
        with self._condition:
            if self._accepting:
                self._unsubscribers.append(unsubscribe)
                return
        try:
            unsubscribe()  # Late registration must release its producer immediately.
        except Exception:
            with self._condition:
                self._unsubscribers.append(unsubscribe)
            raise
        raise RuntimeError("Subscription disposal has already started")

    def emit(self, event: DeviceEvent) -> None:
        """Accept a native event without executing service work on its caller."""
        with self._condition:
            if not self._accepting:
                return
            self._pending += 1
            try:
                self._executor.submit(self._deliver, event)
            except Exception:
                self._pending -= 1
                self._condition.notify_all()
                raise

    def _deliver(self, event: DeviceEvent) -> None:
        with self._condition:
            self._active_thread = threading.get_ident()
        try:
            self._callback(event)
        except Exception as error:
            with self._condition:
                self._errors.append(error)
            bec_logger.logger.exception(
                f"Device event delivery failed for {event.source.qualified_name} "
                f"({event.channel or event.kind}): {error}"
            )
        finally:
            with self._condition:
                self._active_thread = None
                self._pending -= 1
                self._condition.notify_all()

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
        if threading.current_thread().name.startswith("BECDeviceEvents"):
            raise RuntimeError("A subscription cannot close itself from its delivery callback")
        with self._lifecycle:
            self._drain_owned(dispose=dispose)

    def _drain_owned(self, *, dispose: bool) -> None:
        with self._condition:
            if threading.current_thread().name.startswith("BECDeviceEvents"):
                raise RuntimeError("A subscription cannot close itself from its delivery callback")
            self._accepting = False
            self._disposed |= dispose
        errors = []
        with self._condition:
            unsubscribers = self._unsubscribers
            self._unsubscribers = []
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
        if errors or self._errors:
            raise (errors + self._errors)[0]
