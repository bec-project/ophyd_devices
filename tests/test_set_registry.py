"""Regression tests for root-scoped, cooperative Signal.set cancellation."""

from __future__ import annotations

import gc
import inspect
import os
import subprocess
import sys
import threading
import time
import weakref
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest
from ophyd import Component, Device, Signal
from ophyd.utils.errors import DestroyedError, StatusTimeoutError, WaitTimeoutError

from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.utils.set_registry import (
    SetCancelledError,
    install_signal_set_patch,
    set_registry,
)


class PendingSignal(Signal):
    """Accept writes without moving readback, like a stopped hardware device."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.put_started = threading.Event()
        self.put_kwargs = None
        self.get_kwargs = None

    def put(self, value, **kwargs):
        self.put_kwargs = kwargs
        self.put_started.set()

    def get(self, **kwargs):
        self.get_kwargs = kwargs
        return super().get(**kwargs)


class SignalDevice(Device):
    signal = Component(PendingSignal, value=0)


class PSISignalDevice(PSIDeviceBase):
    signal = Component(PendingSignal, value=0)


@pytest.fixture(autouse=True)
def clean_registry():
    yield
    for operation in set_registry.active():
        operation.cancel()
        try:
            operation.status.wait(timeout=2)
        except SetCancelledError:
            pass
    assert not set_registry.active()


def pending_set(signal, value=1, **kwargs):
    status = signal.set(value, **kwargs)
    assert signal.put_started.wait(2)
    operation = next(op for op in set_registry.active(signal.root) if op.signal is signal)
    return status, operation


def assert_cancelled(status):
    with pytest.raises(SetCancelledError):
        status.wait(timeout=2)


def test_root_identity_and_snapshots():
    first = SignalDevice(name="same_name")
    second = SignalDevice(name="same_name")
    first_status, first_operation = pending_set(first.signal)
    second_status, second_operation = pending_set(second.signal)
    assert first_operation.signal is first.signal
    assert first_operation.value == 1
    assert first_operation.status is first_status
    assert first_operation.started_at <= time.monotonic()
    assert set_registry.by_root() == {first: (first_operation,), second: (second_operation,)}
    assert set_registry.active(first.signal) == ()
    assert set_registry.cancel(first) == (first_operation,)
    assert_cancelled(first_status)
    assert not second_status.done
    assert not second_operation.cancel_requested
    second_operation.cancel()
    assert_cancelled(second_status)


@pytest.mark.parametrize("destroy_target", ["signal", "root"])
def test_destroyed_signal_or_root_rejects_new_sets(destroy_target):
    root = Device(name="root")
    # This child is not a Component, so Device.destroy() will not destroy it.
    signal = Signal(name="signal", parent=root, value=0)
    try:
        (signal if destroy_target == "signal" else root).destroy()
        with mock.patch.object(signal, "put") as put:
            with pytest.raises(DestroyedError, match="has been destroyed"):
                signal.set(1)
        put.assert_not_called()
        assert not set_registry.active(root)
        assert signal._set_thread is None
    finally:
        signal.destroy()
        root.destroy()


def test_nested_signals_share_the_root_registry():
    class NestedDevice(Device):
        left = Component(SignalDevice)
        right = Component(SignalDevice)

    device = NestedDevice(name="root")
    left_status, left_operation = pending_set(device.left.signal)
    right_status, right_operation = pending_set(device.right.signal)
    assert set_registry.active(device) == (left_operation, right_operation)
    assert set_registry.by_root() == {device: (left_operation, right_operation)}
    assert set_registry.cancel(device) == (left_operation, right_operation)
    assert_cancelled(left_status)
    assert_cancelled(right_status)


def test_stop_allows_a_subsequent_set():
    device = PSISignalDevice(name="device")
    status, _ = pending_set(device.signal)
    device.stop()
    assert_cancelled(status)
    assert device.signal._set_thread is None
    next_status, next_operation = pending_set(device.signal, 2)
    Signal.put(device.signal, 2)
    next_status.wait(timeout=2)
    assert not next_operation.cancel_requested
    assert not set_registry.active(device)


def test_stop_error_still_cancels_signal_workers():
    device = PSISignalDevice(name="device")
    status, _ = pending_set(device.signal)
    with mock.patch.object(device, "on_stop", side_effect=ValueError("hardware stop failed")):
        with pytest.raises(ValueError, match="hardware stop failed"):
            device.stop()
    assert_cancelled(status)
    # A failed hardware hook must also release the root's set admission gate.
    device.signal.set(0).wait(timeout=2)


def test_external_status_failure_does_not_hide_active_worker():
    signal = PendingSignal(name="signal", value=0)
    status, operation = pending_set(signal)
    thread = signal._set_thread
    status.set_exception(ValueError("driver already stopped"))
    assert status.done
    assert set_registry.active(signal) == (operation,)
    with pytest.raises(RuntimeError, match="Another set"):
        signal.set(2)
    operation.cancel()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert signal._set_thread is None
    assert isinstance(status.exception(), ValueError)
    signal.set(0).wait(timeout=2)


def test_settle_is_registered_and_cancellable():
    signal = Signal(name="signal", value=0)
    status = signal.set(1, settle_time=30)
    (operation,) = set_registry.active(signal)
    operation.cancel()
    assert_cancelled(status)
    signal.set(2).wait(timeout=2)


@pytest.mark.parametrize(
    "readback,target,tolerance",
    [(1, 1, None), (1.01, 1, 0.1), ([1, 2], [1, 2], None), (np.array([1, 2]), [1, 2], None)],
)
def test_success_preserves_comparison_and_put_kwargs(readback, target, tolerance):
    signal = PendingSignal(name="signal", value=readback, tolerance=tolerance)
    signal.set(target, poll_time=0.002, timeout=1, test_kwarg="passed").wait(timeout=2)
    assert signal.put_kwargs == {"test_kwarg": "passed"}
    assert signal.get_kwargs == ({"count": len(target)} if isinstance(target, list) else {})
    assert signal._set_thread is None
    assert not set_registry.active(signal)


def test_enum_comparison():
    class EnumSignal(PendingSignal):
        enum_strs = ("off", "on")

    signal = EnumSignal(name="signal", value=1)
    signal.set("on").wait(timeout=2)


def test_failed_put_and_timeout_cleanup():
    signal = PendingSignal(name="signal", value=0)
    with mock.patch.object(signal, "put", side_effect=ValueError("bad value")):
        with pytest.raises(ValueError, match="bad value"):
            signal.set(1).wait(timeout=2)
    with pytest.raises(TimeoutError):
        signal.set(1, timeout=0.001).wait(timeout=2)
    assert not set_registry.active(signal)
    signal.set(0).wait(timeout=2)


def test_thread_start_failure_rolls_back_registration(monkeypatch):
    signal = Signal(name="signal", value=0)
    with monkeypatch.context() as patch:
        patch.setattr(signal, "cl", SimpleNamespace(thread_class=threading.Thread))
        with mock.patch.object(threading.Thread, "start", side_effect=RuntimeError("no threads")):
            with pytest.raises(RuntimeError, match="no threads"):
                signal.set(1)
    assert signal._set_thread is None
    assert not set_registry.active(signal)
    signal.set(2).wait(timeout=2)


def test_completion_callback_can_start_next_set():
    signal = PendingSignal(name="signal", value=0)
    status, _ = pending_set(signal)
    next_statuses = []
    callback_done = threading.Event()

    def start_next(_):
        next_statuses.append(signal.set(2))
        Signal.put(signal, 2)
        # The next worker needs the registry lock to finish. Waiting here also
        # verifies that callbacks are not invoked while that lock is held.
        next_statuses[0].wait(timeout=2)
        callback_done.set()

    status.add_callback(start_next)
    Signal.put(signal, 1)
    status.wait(timeout=2)
    assert callback_done.wait(2)
    assert signal._status is next_statuses[0]
    assert status is not next_statuses[0]
    next_statuses[0].wait(timeout=2)


def test_custom_hook_without_kwargs_is_tracked_until_it_returns():
    entered = threading.Event()
    release = threading.Event()

    class CustomSignal(Signal):
        # This has the same signature as EpicsPathSignal._set_and_wait.
        def _set_and_wait(self, value, timeout):
            entered.set()
            assert release.wait(2)

    signal = CustomSignal(name="custom")
    status = signal.set(1)
    try:
        assert entered.wait(2)
        (operation,) = set_registry.cancel(signal)
        assert operation.cancel_requested
        assert not status.done
        assert set_registry.active(signal) == (operation,)
    finally:
        release.set()
    assert_cancelled(status)


def test_concurrent_sets_keep_one_worker():
    signal = PendingSignal(name="signal", value=0)
    barrier = threading.Barrier(3)
    statuses = []
    errors = []

    def start_set():
        barrier.wait(timeout=2)
        try:
            statuses.append(signal.set(1))
        except RuntimeError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=start_set) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=2)
    for thread in threads:
        thread.join(timeout=2)
    assert len(statuses) == len(errors) == 1
    assert len(set_registry.active(signal)) == 1
    set_registry.cancel(signal)
    assert_cancelled(statuses[0])


def test_stop_rejects_later_sets_until_hardware_hook_finishes():
    device = PSISignalDevice(name="device")
    status, old_operation = pending_set(device.signal)
    stop_entered = threading.Event()
    release_stop = threading.Event()

    def blocking_stop():
        stop_entered.set()
        assert release_stop.wait(2)

    with mock.patch.object(device, "on_stop", side_effect=blocking_stop):
        thread = threading.Thread(target=device.stop)
        thread.start()
        try:
            assert stop_entered.wait(2)
            # Cancellation must finish while the hardware hook is still blocked.
            assert_cancelled(status)
            with pytest.raises(RuntimeError, match="root device is stopping"):
                device.signal.set(2)
        finally:
            release_stop.set()
            thread.join(timeout=2)
    assert old_operation.cancel_requested
    new_status, new_operation = pending_set(device.signal, 2)
    assert not new_operation.cancel_requested
    assert not new_status.done
    new_operation.cancel()
    assert_cancelled(new_status)


def test_stop_rejects_completion_callback_set_before_hardware_stop_and_allows_retry():
    device = PSISignalDevice(name="device")
    status, _ = pending_set(device.signal)
    callback_done = threading.Event()
    rejected = []

    def start_next(_):
        try:
            device.signal.set(2)
        except RuntimeError as exc:
            rejected.append(exc)
        finally:
            callback_done.set()

    def hardware_stop():
        assert callback_done.wait(2)
        Signal.put(device.signal, 0)

    status.add_callback(start_next)
    with mock.patch.object(device, "on_stop", side_effect=hardware_stop):
        with mock.patch.object(device.signal, "put", wraps=device.signal.put) as put:
            device.stop()
            put.assert_not_called()
    assert_cancelled(status)
    assert len(rejected) == 1
    assert "root device is stopping" in str(rejected[0])
    next_status, _ = pending_set(device.signal, 2)
    Signal.put(device.signal, 2)
    next_status.wait(timeout=2)


def test_direct_operation_cancel_allows_completion_callback_to_start_next_set():
    signal = PendingSignal(name="signal", value=0)
    status, operation = pending_set(signal)
    next_statuses = []
    callback_done = threading.Event()

    def start_next(_):
        next_statuses.append(signal.set(2))
        Signal.put(signal, 2)
        next_statuses[0].wait(timeout=2)
        callback_done.set()

    status.add_callback(start_next)
    operation.cancel()
    assert_cancelled(status)
    assert callback_done.wait(2)
    assert next_statuses[0].success


def test_stopping_many_reserves_other_roots_before_completion_callbacks():
    first = PSISignalDevice(name="first")
    second = PSISignalDevice(name="second")
    status, _ = pending_set(first.signal)
    callback_done = threading.Event()
    rejected = []

    def set_other_root(_):
        try:
            second.signal.set(1)
        except RuntimeError as exc:
            rejected.append(exc)
        finally:
            callback_done.set()

    status.add_callback(set_other_root)
    with set_registry.stopping_many([first, second]):
        assert callback_done.wait(2)
        assert len(rejected) == 1
        assert "root second is stopping" in str(rejected[0])
        # The stop owner can still perform and wait for synchronous cleanup.
        second.signal.set(0).wait(timeout=2)
    second.signal.set(0).wait(timeout=2)


def test_overlapping_stop_scopes_keep_admission_closed_until_both_finish():
    root = Signal(name="root", value=0)
    entered = [threading.Event(), threading.Event()]
    release = [threading.Event(), threading.Event()]

    def stop(index):
        with set_registry.stopping(root):
            entered[index].set()
            assert release[index].wait(2)

    threads = [threading.Thread(target=stop, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    try:
        assert all(event.wait(2) for event in entered)
        with pytest.raises(RuntimeError, match="is stopping"):
            root.set(1)
        release[0].set()
        threads[0].join(timeout=2)
        with pytest.raises(RuntimeError, match="is stopping"):
            root.set(1)
    finally:
        for event in release:
            event.set()
        for thread in threads:
            thread.join(timeout=2)
    root.set(1).wait(timeout=2)


def test_stop_hook_can_wait_for_the_cancelled_set_without_holding_registry_lock():
    device = PSISignalDevice(name="device")
    status, _ = pending_set(device.signal)
    with mock.patch.object(device, "on_stop", side_effect=lambda: assert_cancelled(status)):
        device.stop()
    assert not set_registry.active(device)


def test_subclass_stop_scope_precedes_cleanup_before_super():
    class CleanupDevice(PSISignalDevice):
        def stop(self, *, success=False):
            assert_cancelled(self.old_status)
            self.cleanup_status, self.cleanup_operation = pending_set(self.signal, 2)
            return super().stop(success=success)

    class InheritingDevice(CleanupDevice):
        pass

    assert InheritingDevice.stop is CleanupDevice.stop
    assert inspect.signature(CleanupDevice.stop) == inspect.signature(
        CleanupDevice.stop.__wrapped__
    )
    device = InheritingDevice(name="device")
    device.old_status, _ = pending_set(device.signal)
    device.stop()
    assert not device.cleanup_operation.cancel_requested
    assert not device.cleanup_status.done


def test_mixin_stop_scope_precedes_cleanup_before_super():
    class StopMixin:
        def stop(self, *, success=False):
            self.cleanup_status, self.cleanup_operation = pending_set(self.signal)
            return super().stop(success=success)

    class MixedDevice(StopMixin, PSISignalDevice):
        pass

    device = MixedDevice(name="mixed")
    device.stop()
    assert not device.cleanup_operation.cancel_requested
    assert not device.cleanup_status.done


def test_panda_stop_preserves_sets_started_by_disarm_callbacks():
    from ophyd_devices.devices.panda_box.panda_box import PandaBox, PandaState

    class CleanupPanda(PandaBox):
        signal = Component(PendingSignal, value=0)

    device = CleanupPanda(name="panda", host="localhost")
    cleanup = []
    device.add_data_callback(
        lambda _: cleanup.append(pending_set(device.signal)), data_type=PandaState.DISARMED
    )
    # Exercise the actual PandaBox.stop -> _reset_panda -> callback path.
    with mock.patch.object(device, "_send_command"):
        device.stop()
    ((status, operation),) = cleanup
    assert not operation.cancel_requested
    assert not status.done


def test_stopping_a_child_deliberately_cancels_the_whole_root():
    class RootDevice(PSIDeviceBase):
        left = Component(PSISignalDevice)
        right = Component(PSISignalDevice)

    device = RootDevice(name="root")
    left_status, _ = pending_set(device.left.signal)
    right_status, _ = pending_set(device.right.signal)
    device.left.stop()
    assert_cancelled(left_status)
    assert_cancelled(right_status)


def test_nested_psi_stop_reuses_the_original_root_snapshot():
    class RootDevice(PSIDeviceBase):
        child = Component(PSISignalDevice)

        def on_stop(self):
            self.new_status = self.child.signal.set(1)

    device = RootDevice(name="root")
    assert not set_registry.active(device)
    device.stop()
    (operation,) = set_registry.active(device)
    assert not operation.cancel_requested
    assert not device.new_status.done
    operation.cancel()
    assert_cancelled(device.new_status)


def test_stop_scope_preserves_an_explicit_empty_snapshot():
    device = PSISignalDevice(name="device")
    status, operation = pending_set(device.signal)
    with set_registry.stopping(device, ()):
        device.stop()
    assert not operation.cancel_requested
    assert not status.done
    operation.cancel()
    assert_cancelled(status)


@pytest.mark.parametrize("error_type", [StatusTimeoutError, WaitTimeoutError])
def test_nested_status_timeouts_finish_the_outer_status(error_type):
    error = error_type("nested operation expired")

    class NestedWaitSignal(Signal):
        def _set_and_wait(self, value, timeout):
            raise error

    signal = NestedWaitSignal(name="signal")
    status = signal.set(1)
    with pytest.raises(TimeoutError, match="nested operation expired") as raised:
        status.wait(timeout=2)
    assert type(raised.value) is TimeoutError
    assert raised.value.__cause__ is error
    assert status.done
    assert not set_registry.active(signal)


@pytest.mark.parametrize("grouped", [False, True])
def test_failed_set_releases_hook_buffers_and_keeps_error_diagnostics(caplog, grouped):
    buffers = []

    def fail_with_temporary_buffer():
        temporary = np.empty(1_000_000, dtype="u1")
        buffers.append(weakref.ref(temporary))
        raise ValueError("buffer processing failed")

    class FailedSignal(Signal):
        def _set_and_wait(self, value, timeout):
            try:
                fail_with_temporary_buffer()
            except ValueError as cause:
                if grouped:
                    raise ExceptionGroup("grouped failure", [cause]) from cause
                raise RuntimeError("set processing failed") from cause

    signal = FailedSignal(name="failed")
    status = signal.set(1)
    error = status.exception(timeout=2)
    assert type(error) is (ExceptionGroup if grouped else RuntimeError)
    assert isinstance(error.__cause__, ValueError)
    assert str(error.__cause__) == "buffer processing failed"
    assert "fail_with_temporary_buffer" in caplog.text
    assert "ValueError: buffer processing failed" in caplog.text
    assert error.__traceback__ is None
    assert error.__cause__.__traceback__ is None
    # Keep the captured logging records too: diagnostics must not retain locals.
    gc.collect()
    assert signal._status is status
    assert not set_registry.active(signal)
    assert buffers[0]() is None


def test_cancellation_during_timeout_logging_does_not_retain_the_original_traceback(
    caplog, monkeypatch
):
    buffers = []
    logged = threading.Event()
    release_log = threading.Event()

    class TimedOutSignal(Signal):
        def _set_and_wait(self, value, timeout):
            temporary = np.empty(1_000_000, dtype="u1")
            buffers.append(weakref.ref(temporary))
            raise TimeoutError("timed out with a temporary buffer")

    signal = TimedOutSignal(name="timed_out")
    original_warning = signal.log.warning

    def delayed_warning(*args, **kwargs):
        original_warning(*args, **kwargs)
        logged.set()
        assert release_log.wait(2)

    monkeypatch.setattr(signal.log, "warning", delayed_warning)
    status = signal.set(1)
    worker = signal._set_thread
    try:
        assert logged.wait(2)
        set_registry.cancel(signal)
    finally:
        release_log.set()
        worker.join(timeout=2)
    assert_cancelled(status)
    assert "timed out with a temporary buffer" in caplog.text
    # Retain the warning records while checking collection of the superseded
    # exception's frame locals; cancellation replaced the reported failure.
    gc.collect()
    assert buffers[0]() is None


def test_duplicate_tolerance_kwarg_fails_before_put():
    signal = PendingSignal(name="signal", value=0)
    with pytest.raises(TypeError, match="atol"):
        signal.set(1, atol=0.1).wait(timeout=2)
    assert signal.put_kwargs is None


def test_idempotent_install_preserves_callable_metadata():
    patched_set = Signal.set
    patched_hook = Signal._set_and_wait
    install_signal_set_patch()
    assert Signal.set is patched_set
    assert Signal._set_and_wait is patched_hook
    assert Signal.set.__name__ == "set"
    assert inspect.signature(Signal.set) == inspect.signature(Signal.set.__wrapped__)


def test_install_reaches_preexisting_imports_instances_and_components():
    # conftest imports ophyd_devices, so use a fresh process for import ordering.
    code = """
from ophyd import Signal as EarlySignal, Component, Device
from ophyd.signal import Signal as EarlyModuleSignal

class EarlySubclass(EarlySignal):
    pass

class EarlyDevice(Device):
    signal = Component(EarlySubclass, value=0)

device = EarlyDevice(name='early')
existing = device.signal
import ophyd_devices
from ophyd_devices.utils.set_registry import set_registry, SetCancelledError
assert EarlySignal is EarlyModuleSignal
assert EarlySignal.set.__name__ == 'set'
status = existing.set(1, settle_time=30)
operation, = set_registry.active(device)
operation.cancel()
try:
    status.wait(timeout=2)
except SetCancelledError:
    pass
else:
    raise AssertionError('Existing component did not use the patch')
assert existing._set_thread is None
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "OPHYD_CONTROL_LAYER": "dummy"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_reload_preserves_active_workers_aliases_and_original_methods():
    code = """
import importlib
from ophyd import Signal
import ophyd_devices
from ophyd_devices.interfaces.base_classes.psi_device_base import PSIDeviceBase
from ophyd_devices.utils.set_registry import SetCancelledError, SetOperation, set_registry

module = importlib.import_module('ophyd_devices.utils.set_registry')
root = PSIDeviceBase(name='root')
signal = Signal(name='signal', parent=root)
status = signal.set(1, settle_time=30)
operation, = set_registry.active(root)
worker = signal._set_thread
original_set = module._original_set
original_hook = module._original_set_and_wait
for _ in range(2):
    importlib.reload(module)
    module.install_signal_set_patch()
    assert module.set_registry is set_registry is ophyd_devices.set_registry
    assert module.SetCancelledError is SetCancelledError
    assert module.SetOperation is SetOperation
    assert module._original_set is original_set
    assert module._original_set_and_wait is original_hook
    assert module.set_registry.active(root) == (operation,)
root.stop()
try:
    status.wait(timeout=2)
except SetCancelledError:
    pass
else:
    raise AssertionError('Reloaded worker was not cancelled')
worker.join(timeout=2)
assert not worker.is_alive()
assert signal._set_thread is None
assert not set_registry.active(root)
signal.set(2).wait(timeout=2)
# The original hook must remain callable outside a set worker after reload.
signal._set_and_wait(3, 1)
assert signal.get() == 3
# Previously imported installer and registry aliases work for future operations.
status = signal.set(4, settle_time=30)
operation, = set_registry.active(root)
operation.cancel()
try:
    status.wait(timeout=2)
except SetCancelledError:
    pass
else:
    raise AssertionError('New worker was not cancelled after reload')
assert not set_registry.active(root)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "OPHYD_CONTROL_LAYER": "dummy"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
