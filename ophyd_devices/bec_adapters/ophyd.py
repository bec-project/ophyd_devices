"""Existing ophyd behavior behind BEC's per-device handler interface."""

# Provider and handler jointly own private lifecycle state within this package.
# pylint: disable=protected-access
from __future__ import annotations

import copy
import functools
import inspect
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Concatenate, ParamSpec, TypeVar

from bec_lib import messages
from bec_lib.bec_errors import DeviceConfigError
from bec_lib.device_backend import (
    Capability,
    Completion,
    ConfigurationResult,
    DeviceEvent,
    DeviceIdentity,
    EventContext,
    EventKind,
    MessageChannel,
    Operation,
    OperationMetadata,
    ReadCategory,
    Readings,
    RPCResult,
)
from bec_lib.utils.rpc_utils import rgetattr
from ophyd import Signal
from ophyd.device import Staged
from ophyd.ophydobj import Kind
from ophyd.status import DeviceStatus as NativeDeviceStatus
from ophyd.status import StatusBase

from ophyd_devices.bec_adapters.events import EventSubscription
from ophyd_devices.bec_adapters.serialization import (
    disable_lazy_wait_for_connection,
    get_device_info,
    is_serializable,
)
from ophyd_devices.bec_adapters.values import convert_value
from ophyd_devices.utils import bec_signals as bms

if TYPE_CHECKING:
    from ophyd_devices.bec_adapters.provider import OphydProvider


class DeviceClosedError(RuntimeError):
    """Device ownership ended before an observed operation completed."""


class DeviceRecoveryError(RuntimeError):
    """A prior failed command still owns native stop/recovery for this tree."""


P = ParamSpec("P")
R = TypeVar("R")


def _admitted(
    method: Callable[Concatenate[OphydHandler, P], R], *, during_recovery: bool = False
) -> Callable[Concatenate[OphydHandler, P], R]:
    """Serialize admission/native method invocation, never an acquisition await."""

    @functools.wraps(method)
    def invoke(self: OphydHandler, *args: P.args, **kwargs: P.kwargs) -> R:
        owner = self.provider.owner(self)
        with owner._admission:
            if self.provider._closing or owner._closing or owner._closed:
                raise DeviceClosedError("Device is closing")
            if owner._recovering and not during_recovery:
                raise DeviceRecoveryError(
                    "Device is stopping after a failed command; retry after recovery"
                )
            owner._inflight += 1
        try:
            return method(self, *args, **kwargs)
        finally:
            with owner._idle:
                owner._inflight -= 1
                owner._idle.notify_all()

    return invoke


def _admitted_observation(
    method: Callable[Concatenate[OphydHandler, P], R],
) -> Callable[Concatenate[OphydHandler, P], R]:
    """Keep resolution and event observation available while recovery owns commands."""
    return _admitted(method, during_recovery=True)


class OphydHandler:  # pylint: disable=too-many-public-methods
    """Bound adapter; the provider and library own its raw device."""

    def __init__(self, device: Any, provider: OphydProvider) -> None:
        self.device = device
        self.provider = provider
        self._subscriptions: list[EventSubscription] = []
        self._closed = False
        self._closing = False
        self._admission = threading.RLock()
        self._idle = threading.Condition(self._admission)
        self._inflight = 0
        self._recovering = 0
        self._pending: set[Operation[None]] = set()

    @property
    def identity(self) -> DeviceIdentity:
        """Configured root, requested child path and published native name."""
        device = self.device
        root = getattr(device, "root", device)
        return DeviceIdentity(
            root.name, getattr(device, "dotted_name", ""), getattr(device, "name", root.name)
        )

    @property
    def capabilities(self) -> frozenset[Capability]:
        """Optional operations supported by this handler."""
        result = set()
        if isinstance(self.device, Signal):
            result.add(Capability.SIGNAL)
        if hasattr(self.device, "_staged"):
            result.add(Capability.STAGE)
        for capability in (
            Capability.PRE_SCAN,
            Capability.COMPLETE,
            Capability.KICKOFF,
            Capability.SET,
            Capability.STOP,
        ):
            if callable(getattr(self.device, capability.value, None)):
                result.add(capability)
        if hasattr(self.device, "lookup"):
            result.add(Capability.PROXY)
        return frozenset(result)

    @property
    def connected(self) -> bool:
        """Whether the device is available and has not been closed."""
        return self.device.connected and not self._closed

    @property
    def staged(self) -> bool:
        """Whether staging has completed according to the provider."""
        return getattr(self.device, "_staged", None) == Staged.yes

    @property
    def read_category(self) -> ReadCategory:
        """Select the existing BEC read/configuration cache membership."""
        kind = getattr(self.device, "kind", Kind.normal)
        if kind == Kind.config:
            return ReadCategory.CONFIGURATION
        if kind in (Kind.normal, Kind.hinted):
            return ReadCategory.NORMAL
        return ReadCategory.OMITTED if kind == Kind.omitted else ReadCategory.MIXED

    @_admitted_observation
    def resolve(self, path: str) -> OphydHandler:
        """Resolve a child path while retaining the requested target identity."""
        return self.provider.wrap(rgetattr(self.device, path)) if path else self

    @_admitted
    def connect(self, *, all_signals: bool = False, timeout: float = 5) -> None:
        """Establish connection with the provider-specific bounded startup timeout."""
        if hasattr(self.device, "wait_for_connection"):
            try:
                with disable_lazy_wait_for_connection(self.device):
                    self.device.wait_for_connection(all_signals=all_signals, timeout=timeout)
            except TypeError:
                with disable_lazy_wait_for_connection(self.device):
                    self.device.wait_for_connection(timeout=timeout)
        elif not self.connected:
            raise ConnectionError(
                f"Failed to establish a connection to device {self.identity.root}"
            )

    @_admitted
    def on_connected(self) -> None:
        """Invoke the existing optional post-connection hook."""
        hook = getattr(self.device, "on_connected", None)
        if hook is not None:
            hook()

    def describe(self, *, connected: bool = True) -> dict:
        """Return existing offline or connected device metadata."""
        return get_device_info(self.device, connect=connected)

    def read(self) -> Readings:
        """Read normal data using the existing BEC value/timestamp projection."""
        if self._closed:
            raise DeviceClosedError("Device is closed")
        with self.provider.reading(self.identity.root):
            return self.device.read()

    def read_configuration(self) -> Readings:
        """Read configuration data using the existing BEC projection."""
        if self._closed:
            raise DeviceClosedError("Device is closed")
        with self.provider.reading(self.identity.root):
            return self.device.read_configuration()

    def limits(self) -> Readings | None:
        """Return low/high limit values when supported, otherwise None."""
        if hasattr(self.device, "low_limit_travel") and hasattr(self.device, "high_limit_travel"):
            return {
                "low": {"value": self.device.low_limit_travel.get()},
                "high": {"value": self.device.high_limit_travel.get()},
            }
        return None

    @_admitted
    def configure(self, values: dict) -> ConfigurationResult:
        """Apply the provider-native configuration and report cache-refresh intent."""
        if hasattr(self.device, "_update_device_config"):
            self.device._update_device_config(values)  # pylint: disable=protected-access
            return ConfigurationResult(delegated=True)
        updated = False
        for key, value in values.items():
            if key == "limits" and all(
                hasattr(self.device, attr) for attr in ("low_limit_travel", "high_limit_travel")
            ):
                low = self.device.low_limit_travel.set(value[0])
                high = self.device.high_limit_travel.set(value[1])
                low.wait(timeout=2)
                high.wait(timeout=2)
                continue
            if key == "labels":
                self.device._ophyd_labels_ = set(value or ())  # pylint: disable=protected-access
                continue
            if not hasattr(self.device, key):

                raise DeviceConfigError(
                    f"Unknown config parameter {key} for device of type {type(self.device).__name__}."
                )
            member = getattr(self.device, key)
            if isinstance(member, Signal):
                member.set(value).wait(timeout=2)
                updated |= not hasattr(member, "_auto_monitor")
            elif callable(member):
                member(value)
            else:
                setattr(self.device, key, value)
        return ConfigurationResult(refresh=updated)

    def operation(self, native: Any) -> Completion[None]:
        """Pure outcome adaptation; do not duplicate native failure/stop hooks."""
        if not isinstance(native, StatusBase):
            raise ValueError("The device operation does not return a StatusBase object.")
        owner = self.provider.owner(self)
        operation: Operation[None] = Operation(
            None if native.done else self.provider.dispatch_callback
        )
        with owner._admission:
            if owner._closed:
                return Operation.failed(DeviceClosedError("Device closed during submission"))
            owner._pending.add(operation)

        def finished(status: StatusBase) -> None:
            with owner._admission:
                if operation.done:
                    return
                error = status.exception(timeout=0)
                owner._pending.discard(operation)
                if error is not None:
                    operation.set_exception(error)
                else:
                    operation.set_result(None)

        native.add_callback(finished)
        return operation

    @_admitted
    def set(self, value: Any) -> Completion[None]:
        """Submit a native write/move and return its neutral completion."""
        try:
            return self.operation(self.device.set(self.convert_value(value)))
        except Exception as error:
            # Preserve the native failure-stop policy, but own the possibly
            # blocking stop outside request and completion workers.
            def failed_submission(error: Exception = error) -> None:
                failure = NativeDeviceStatus(device=self.device)
                failure.set_exception(error)

            try:
                self.provider.recover_failed_set(self, failed_submission)
            except Exception as cleanup_error:
                error.add_note(f"Native failure recovery could not be scheduled: {cleanup_error!r}")
            raise

    def convert_value(self, value: Any) -> Any:
        """Preserve integral-float enum conversion, including numpy scalars."""
        return convert_value(self.device, value)

    @_admitted
    def trigger(self) -> Completion[None]:
        """Submit acquisition and return its neutral completion."""
        return self.operation(self.device.trigger())

    @_admitted
    def stage(self) -> Completion[None] | None:
        """Submit staging, preserving legacy immediate versus pending results."""
        value = self.device.stage()
        return None if value is None or isinstance(value, list) else self.operation(value)

    @_admitted
    def unstage(self) -> Completion[None] | None:
        """Submit unstaging, preserving legacy immediate versus pending results."""
        value = self.device.unstage()
        return None if value is None or isinstance(value, list) else self.operation(value)

    @_admitted
    def pre_scan(self) -> Completion[None] | None:
        """Submit optional pre-scan work and normalize its result."""
        value = self.device.pre_scan()
        return None if value is None else self.operation(value)

    @_admitted
    def kickoff(self, configure: dict, metadata: dict) -> Completion[None] | None:
        """Adapt existing legacy and standard kickoff signatures."""
        if len(inspect.getfullargspec(self.device.kickoff).args) > 1:
            self.device.kickoff(metadata=metadata, **configure)
            return None
        self.device.configure(configure)
        return self.operation(self.device.kickoff())

    @_admitted
    def complete(self) -> Completion[None] | None:
        """Submit completion work and normalize its result."""
        value = self.device.complete()
        return None if value is None else self.operation(value)

    def stop(self) -> Completion[None]:
        """Invoke native hardware stop independently of pending native submissions."""
        self.device.stop()
        return Operation.finished(None)

    def _listen(  # pylint: disable=too-many-arguments
        self,
        subscription: EventSubscription,
        device: Any,
        kind: EventKind,
        *,
        event_type=None,
        run=False,
        batched=False,
        channel=None,
    ) -> None:
        identity = self.provider.wrap(device).identity

        def callback(*_args, value=None, **_kwargs):
            ancestry = self.provider.read_roots()
            if (
                kind in (EventKind.READBACK, EventKind.CONFIGURATION, EventKind.LIMITS)
                and identity.root in ancestry
            ):
                return
            if not getattr(device, "connected", True):
                return
            event_context = (
                subscription.context()
                if kind == EventKind.MESSAGE and subscription.context is not None
                else None
            )
            # Producers may reuse messages and ndarray buffers immediately after put.
            # Snapshot exactly once before the off-owner handoff.
            message = value.model_copy(deep=True) if kind == EventKind.MESSAGE else None
            metadata = (
                copy.deepcopy(device.signal_info.signal_metadata)
                if channel == MessageChannel.DYNAMIC
                else None
            )
            subscription.emit(
                DeviceEvent(
                    identity,
                    kind,
                    batched,
                    value=(
                        copy.deepcopy(value)
                        if kind == EventKind.MOTION or subscription.registration == "readback"
                        else None
                    ),
                    message=message,
                    channel=channel,
                    signal_metadata=metadata,
                    context=event_context,
                ),
                ancestry=ancestry,
            )

        device.subscribe(callback, event_type=event_type, run=run)
        subscription.own(lambda: device.clear_sub(callback, event_type=event_type))

    @_admitted_observation
    def subscribe(
        self,
        callback: Callable[[DeviceEvent], None],
        *,
        context: Callable[[], EventContext] | None = None,
    ) -> EventSubscription:
        """Register pushed events and return the owned disposal token."""
        subscription = EventSubscription(
            self.provider.events, callback, context=context, delivery_scope=self.provider.receiving
        )
        self._subscriptions.append(subscription)
        subscription.on_close = lambda: (
            self._subscriptions.remove(subscription)
            if subscription in self._subscriptions
            else None
        )
        try:
            self._register_events(subscription)
        except Exception:
            subscription.close()
            raise
        return subscription

    def _register_events(self, subscription: EventSubscription) -> None:
        if subscription.registration == "readback":
            events = getattr(self.device, "event_types", ())
            if "readback" in events or "value" in events:
                self._listen(subscription, self.device, EventKind.READBACK, run=True)
            return
        events = getattr(self.device, "event_types", ())
        if "readback" in events:
            self._listen(
                subscription, self.device, EventKind.READBACK, event_type="readback", run=True
            )
        elif "value" in events:
            self._listen(
                subscription, self.device, EventKind.READBACK, event_type="value", run=True
            )
        if "done_moving" in events:
            self._listen(subscription, self.device, EventKind.READBACK, event_type="done_moving")
        if hasattr(self.device, "motor_is_moving"):
            self._listen(subscription, self.device.motor_is_moving, EventKind.MOTION, run=True)
        for attr in ("low_limit_travel", "high_limit_travel"):
            signal = getattr(self.device, attr, None)
            if signal is not None and hasattr(signal, "subscribe"):
                self._listen(subscription, signal, EventKind.LIMITS, batched=True)
        self._monitor_children(subscription, self.device)
        for _, signal in self._message_signals():
            channel = next(
                (
                    channel
                    for cls, channel in (
                        (bms.FileEventSignal, MessageChannel.FILE),
                        (bms.ProgressSignal, MessageChannel.PROGRESS),
                        (bms.PreviewSignal, MessageChannel.PREVIEW),
                        (bms.DynamicSignal, MessageChannel.DYNAMIC),
                    )
                    if isinstance(signal, cls)
                ),
                None,
            )
            if channel is not None:
                self._listen(subscription, signal, EventKind.MESSAGE, channel=channel)

    def _monitor_children(self, subscription: EventSubscription, device: Any) -> None:
        for name in getattr(device, "component_names", ()):
            child = getattr(device, name)
            if hasattr(child, "component_names"):
                self._monitor_children(subscription, child)
            elif getattr(child, "_auto_monitor", False):
                if child.kind in (Kind.normal, Kind.hinted):
                    self._listen(subscription, child, EventKind.READBACK, batched=True)
                elif child.kind == Kind.config:
                    self._listen(subscription, child, EventKind.CONFIGURATION, batched=True)

    def flush_events(self, timeout: float = 10) -> None:
        """Fence accepted service publication without changing native outcomes."""
        self.provider.flush_tree_events(self, timeout)

    @_admitted_observation
    def subscribe_readback(self, callback: Callable[[DeviceEvent], None]) -> EventSubscription:
        """Register temporary requested-target readback observation."""
        subscription = EventSubscription(
            self.provider.events, callback, delivery_scope=self.provider.receiving
        )
        subscription.registration = "readback"
        self._subscriptions.append(subscription)
        subscription.on_close = lambda: (
            self._subscriptions.remove(subscription)
            if subscription in self._subscriptions
            else None
        )
        try:
            self._register_events(subscription)
        except Exception:
            subscription.close()
            raise
        return subscription

    def _message_signals(self):
        if isinstance(self.device, bms.BECMessageSignal):
            yield "", self.device
        elif hasattr(self.device, "walk_signals"):
            for _, name, signal in self.device.walk_signals():
                if isinstance(signal, bms.BECMessageSignal):
                    yield name, signal

    def runtime_info(self) -> dict[str, messages.SignalInfo]:
        """Return live BEC push-signal descriptions without connecting hardware."""
        return {name: signal.signal_info for name, signal in self._message_signals()}

    @_admitted
    def rpc(self, path: str, args: tuple, kwargs: dict, *, rid: str | None = None) -> RPCResult:
        """Invoke an existing RPC path and normalize its value or pending result."""
        member = rgetattr(self.device, path)
        target_path = path.rsplit(".", 1)[0] if path.endswith((".set", ".put", ".read")) else ""
        target = self.resolve(target_path)
        if path.endswith(("set", "put")) and isinstance(target.device, Signal) and args:
            args = (target.convert_value(args[0]), *args[1:])
        result = member(*args, **kwargs) if callable(member) else member
        refresh = (
            path == "set"
            or path.endswith(".set")
            or path == "put"
            or path.endswith(".put")
            or path == "get"
            or path.endswith(".get")
        )
        if isinstance(result, StatusBase):
            status = OperationMetadata(
                result.success, result.timeout, result.done, result.settle_time
            )
            return RPCResult(
                completion=self.operation(result),
                status=status,
                target_path=target_path,
                refresh=refresh,
            )
        if isinstance(result, list) and result and isinstance(result[0], Staged):
            result = [str(state) for state in result]
        if not is_serializable(result):
            if isinstance(result, list) and path in ("stage", "unstage"):
                result = [item._staged for item in result]  # pylint: disable=protected-access
            else:
                parameters = {"func": path, "args": list(args), "kwargs": kwargs}
                text = f"Return value of rpc call {parameters} is not serializable."
                return RPCResult(
                    warning=messages.ErrorInfo(
                        error_message=text,
                        compact_error_message=text,
                        exception_type="TypeError",
                        device=self.identity.root,
                    ),
                    target_path=target_path,
                    refresh=refresh,
                )
        if isinstance(result, tuple) and hasattr(result, "_asdict") and hasattr(result, "_fields"):
            result = {
                "type": "namedtuple",
                "RID": rid,
                "fields": result._fields,
                "values": result._asdict(),
            }
        if isinstance(result, list) and result and isinstance(result[0], Staged):
            result = [str(state) for state in result]
        return RPCResult(value=result, target_path=target_path, refresh=refresh)

    @_admitted
    def set_property(self, path: str, value: Any) -> None:
        """Write an existing RPC-exposed property through native execution."""
        parent, _, attribute = path.rpartition(".")
        target = rgetattr(self.device, parent) if parent else self.device
        setattr(target, attribute, value)

    def close(self) -> None:
        """Close the whole owned tree, including resolved child subscriptions."""
        self.provider.close_tree(self)
