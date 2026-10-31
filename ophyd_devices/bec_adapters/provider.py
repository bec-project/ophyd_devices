"""Device-library provider for existing synchronous ophyd/device implementations."""

# Provider and handler jointly own private lifecycle state within this package.
# pylint: disable=protected-access
from __future__ import annotations

import inspect
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager
from typing import Any

import ophyd
from bec_lib import plugin_helper
from bec_lib.bec_errors import DeviceConfigError
from bec_lib.device_backend import DeviceHandler
from ophyd import OphydObject, Signal
from ophyd.signal import EpicsSignalBase

import ophyd_devices as opd
from ophyd_devices.bec_adapters.diagnostics import OphydCallbackMonitor
from ophyd_devices.bec_adapters.logging import configure_logging
from ophyd_devices.bec_adapters.ophyd import DeviceClosedError, OphydHandler


class OphydProvider:
    """Own handler instances, native adaptation and callback infrastructure."""

    def __init__(self) -> None:
        configure_logging()
        self.events = ThreadPoolExecutor(max_workers=1, thread_name_prefix="BECDeviceEvents")
        self.callbacks = ThreadPoolExecutor(max_workers=4, thread_name_prefix="BECDeviceCompletion")
        self._lock = threading.RLock()
        self._close_lock = threading.RLock()
        self._construction_idle = threading.Condition(self._lock)
        self._constructing = 0
        self._closing = False
        self._callbacks_closed = False
        self._callback_futures = set()
        self._callback_errors = []
        self._reads = threading.local()
        self._handlers: dict[int, OphydHandler] = {}
        self._closed = False

    def load_class(self, specification: str) -> type:
        """Resolve an allowed configured device class through the provider."""
        return plugin_helper.get_plugin_class(specification, [opd, ophyd])

    def construct(
        self, device_class: type, config: dict, context: Any = None
    ) -> tuple[object, dict]:
        """Construct and own a native object while preserving unused configuration."""
        with self._construction_idle:
            if self._closed or self._closing:
                raise DeviceClosedError("Device provider is closing")
            self._constructing += 1
        try:
            device, remaining = self._construct(device_class, config, context)
            with self._lock:
                # An admitted constructor may finish while close is fencing new
                # work. Register ownership before notifying the bounded closer.
                self._handlers[id(device)] = OphydHandler(device, self)
            return device, remaining
        finally:
            with self._construction_idle:
                self._constructing -= 1
                self._construction_idle.notify_all()

    def _construct(self, device_class: type, config: dict, context: Any) -> tuple[object, dict]:
        config = config.copy()
        classes = [device_class]
        for base in (Signal, EpicsSignalBase, OphydObject):
            if issubclass(device_class, base):
                classes.append(base)
        parameters = set()
        for cls in classes:
            parameters.update(inspect.signature(cls).parameters)
        kwargs = {key: config.pop(key) for key in parameters & config.keys()}
        access = config.pop("device_access", None)
        if access or (access is None and config.get("device_mapping")):
            kwargs["device_manager"] = context
        signature = inspect.signature(device_class)
        if "device_manager" in signature.parameters:
            kwargs["device_manager"] = context
        if "scan_info" in signature.parameters:
            kwargs["scan_info"] = context.scan_info if context else None
        return device_class(**kwargs), config

    def wrap(self, device: object) -> OphydHandler:
        """Bind a native object to an owned per-device handler."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Device provider is closed")
            if getattr(device, "_destroyed", False) is True:
                raise DeviceClosedError("Cannot bind a destroyed device")
            root = getattr(device, "root", device)
            owner = self._handlers.get(id(root))
            if owner is not None and (owner._closing or owner._closed):
                raise DeviceClosedError("Device tree is closing")
            handler = self._handlers.get(id(device))
            if handler is None or handler.device is not device:
                if self._closing:
                    raise RuntimeError("Device provider is closing")
                # Register tree ownership before any child can own subscriptions.
                root = getattr(device, "root", device)
                if root is not device and id(root) not in self._handlers:
                    self._handlers[id(root)] = OphydHandler(root, self)
                handler = OphydHandler(device, self)
                self._handlers[id(device)] = handler
            return handler

    def requires_dependencies(self, device_class: type) -> bool:
        """Whether construction needs the existing dependency-resolution pass."""
        return issubclass(device_class, (opd.DeviceProxy, opd.ComputedSignal))

    def register_proxy(self, proxy: DeviceHandler, devices: Mapping[str, DeviceHandler]) -> None:
        """Register provider-native proxy dependencies without exposing them to BEC."""
        if not isinstance(proxy, OphydHandler):
            raise TypeError("An ophyd proxy requires an ophyd handler")
        name = proxy.identity.root
        for key, info in proxy.device.lookup.items():
            signal = info.get("signal_name")
            if key not in devices:
                raise DeviceConfigError(
                    f"Failed to init DeviceProxy {name}, no device {key} found in device manager."
                )
            handler = devices[key]
            if not isinstance(handler, OphydHandler):
                raise DeviceConfigError(
                    "A legacy proxy cannot use an asynchronous/native dependency"
                )
            raw = handler.device
            registered = raw.registered_proxies
            if not hasattr(raw, signal):
                raise DeviceConfigError(
                    f"Failed to init DeviceProxy {name}, no signal {signal} found for device {key}."
                )
            if key not in registered or signal not in registered[key]:
                raw._registered_proxies.update({name: signal})  # pylint: disable=protected-access
            else:
                raise RuntimeError(
                    f"Failed to init DeviceProxy {name}, device {key} already has a registered DeviceProxy for {signal}. Only one DeviceProxy can be active per signal."
                )

    def callback_monitor(self) -> OphydCallbackMonitor:
        """Create native callback diagnostics behind the neutral monitor contract."""
        return OphydCallbackMonitor(queue_threshold=1000)

    def dispatch_callback(self, callback: Callable[[], None]) -> None:
        """Queue service completion observers outside native callback execution."""
        with self._lock:
            if self._callbacks_closed:
                future = None
            else:
                future = self.callbacks.submit(callback)
                self._callback_futures.add(future)
        if future is None:
            # All native producers have been fenced and settled. A late observer
            # may still subscribe to a terminal operation after provider close;
            # deliver on that observer's caller, never a retired HAL context.
            callback()
            return

        def finished(done):
            with self._lock:
                self._callback_futures.discard(done)
                if done.exception() is not None:
                    self._callback_errors.append(done.exception())

        future.add_done_callback(finished)

    def error_device(self, error: BaseException) -> str | None:
        """Identify the native owner of an error, when available."""
        tb = error.__traceback__
        while tb:
            obj = tb.tb_frame.f_locals.get("self")
            if isinstance(obj, OphydObject):
                return obj.dotted_name or obj.name
            tb = tb.tb_next
        return None

    @contextmanager
    def reading(self, root: str):
        """Suppress only same-thread invalidations caused by the snapshot being read.

        Computed legacy signals can emit value updates from get(). Their original
        inline callback guard prevented recursive reads; queued delivery needs an
        explicit snapshot scope. Transport updates on other threads are unaffected.
        """
        active = getattr(self._reads, "active", {})
        self._reads.active = active
        active[root] = active.get(root, 0) + 1
        try:
            yield
        finally:
            active[root] -= 1
            if not active[root]:
                active.pop(root)

    def is_reading(self, root: str) -> bool:
        """Whether this thread is taking a snapshot for the configured root."""
        return bool(getattr(self._reads, "active", {}).get(root))

    def owner(self, handler: OphydHandler) -> OphydHandler:
        """Return the registered root ownership domain without admitting new work."""
        root = getattr(handler.device, "root", handler.device)
        with self._lock:
            return self._handlers.get(id(root), handler)

    def close_tree(self, handler: OphydHandler) -> None:  # pylint: disable=too-many-branches
        """Fence submission, drain every descendant and settle pending observers."""
        with self._close_lock:
            owner = self.owner(handler)
            if owner._closed:
                return
            with owner._admission:
                with self._lock:
                    owner._closing = True
                if not owner._idle.wait_for(lambda: owner._inflight == 0, timeout=10):
                    raise TimeoutError("Timed out draining native device submissions")
                with self._lock:
                    tree = [item for item in self._handlers.values() if self.owner(item) is owner]
            errors = []
            registrations = [
                (item, subscription) for item in tree for subscription in item._subscriptions
            ]
            for item in tree:
                for subscription in tuple(item._subscriptions):
                    try:
                        subscription.suspend()
                    except TimeoutError:
                        # Keep ownership/infrastructure for a retry; never perform an
                        # unbounded Executor.shutdown after a bounded drain failure.
                        raise
                    except Exception as error:
                        errors.append(error)
            try:
                destroy = getattr(owner.device, "destroy", None)
                if destroy is not None:
                    destroy()
            except Exception as error:
                # Preserve a live legacy device after failed disable and allow retry.
                # Subscription registrations were removed before the failed destroy.
                with owner._admission:
                    owner._closing = False
                for item, subscription in registrations:
                    try:
                        subscription.resume(
                            lambda item=item, subscription=subscription: item._register_events(
                                subscription
                            )
                        )
                    except Exception as restore_error:
                        error.add_note(f"Subscription restoration failed: {restore_error!r}")
                raise
            for _, subscription in registrations:
                try:
                    subscription.close()
                except Exception as error:
                    errors.append(error)
            with owner._admission:
                for operation in tuple(owner._pending):
                    if not operation.done:
                        operation.set_exception(
                            DeviceClosedError("Device closed before completion")
                        )
                owner._pending.clear()
                for item in tree:
                    item._closed = True
            with self._lock:
                for item in tree:
                    if self._handlers.get(id(item.device)) is item:
                        self._handlers.pop(id(item.device))
            if errors:
                raise errors[0]

    def close(self) -> None:
        """Fence new work, drain owned delivery and release resources or raise."""
        with self._close_lock:
            with self._lock:
                if self._closed:
                    return
                self._closing = True
                if not self._construction_idle.wait_for(
                    lambda: self._constructing == 0, timeout=10
                ):
                    raise TimeoutError("Timed out draining device constructors")
                handlers = tuple(self._handlers.values())
            errors = []
            for handler in handlers:
                if self.owner(handler) is handler:
                    try:
                        self.close_tree(handler)
                    except TimeoutError:
                        raise
                    except Exception as error:
                        errors.append(error)
            if any(not handler._closed for handler in handlers):
                # Cleanup failed: retain infrastructure and ownership for a retry.
                raise errors[0] if errors else RuntimeError("Device ownership did not close")
            with self._lock:
                self._callbacks_closed = True
                pending = tuple(self._callback_futures)
            if pending:
                _, not_done = wait(pending, timeout=10)
                if not_done:
                    raise TimeoutError("Timed out draining device completion callbacks")
            self.events.shutdown(wait=True)
            self.callbacks.shutdown(wait=True)
            with self._lock:
                self._closed = True
                self._handlers.clear()
                errors.extend(self._callback_errors)
            if errors:
                raise errors[0]
