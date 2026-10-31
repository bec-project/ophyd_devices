"""Behavioral contracts of the existing-device adapter and its owned resources."""

from __future__ import annotations

import gc
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor

import pytest
from bec_lib import messages
from bec_lib.device_backend import DeviceEvent, DeviceIdentity, EventKind, MessageChannel
from ophyd import Component as Cpt
from ophyd import Device, Signal
from ophyd.status import StatusBase

from ophyd_devices.bec_adapters import OphydProvider
from ophyd_devices.bec_adapters.events import EventSubscription
from ophyd_devices.bec_adapters.ophyd import DeviceClosedError
from ophyd_devices.utils.bec_signals import FileEventSignal


class Tree(Device):
    value = Cpt(Signal, value=0)
    file = Cpt(FileEventSignal)


@pytest.fixture
def provider():
    instance = OphydProvider()
    yield instance
    instance.close()


def test_pending_native_status_has_a_terminal_observer_before_provider_closes(provider):
    raw = Device(name="detector")
    handler = provider.wrap(raw)
    native = StatusBase()
    observed = []
    operation = handler.operation(native)
    operation.add_callback(lambda completed: observed.append(completed.exception()))
    provider.close()
    assert operation.done
    assert len(observed) == 1
    assert isinstance(observed[0], DeviceClosedError)
    native.set_finished()  # Late native notification must not target a closed executor.
    assert len(observed) == 1


def test_successfully_closed_trees_are_not_retained_by_registry(provider):
    references = []
    for index in range(5):
        raw = Tree(name=f"tree{index}")
        references.append(weakref.ref(raw))
        handler = provider.wrap(raw)
        handler.resolve("value")
        handler.close()
    del raw, handler
    gc.collect()
    assert not provider._handlers
    assert all(reference() is None for reference in references)


def test_temporary_readback_subscriptions_release_ownership(provider):
    handler = provider.wrap(Tree(name="tree")).resolve("value")
    for _ in range(20):
        subscription = handler.subscribe_readback(lambda event: None)
        subscription.close()
    assert handler._subscriptions == []


def test_root_close_drains_resolved_child_callbacks(provider):
    raw = Tree(name="tree")
    root = provider.wrap(raw)
    child = root.resolve("value")
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    observed = []

    def callback(event):
        if event.value == 1:
            entered.set()
            assert release.wait(2)
        observed.append(event.value)

    child.subscribe_readback(callback)
    raw.value.put(1)
    assert entered.wait(2)
    closer = threading.Thread(target=lambda: (root.close(), closed.set()))
    closer.start()
    try:
        assert not closed.wait(0.05)
        release.set()
        assert closed.wait(2)
        assert 1 in observed
        previous = list(observed)
        # Closed subscription receives no subsequent producer notification.
        assert child._subscriptions == []
        assert observed == previous
    finally:
        release.set()
        closer.join(2)


def test_file_message_is_snapshotted_before_queued_delivery(provider):
    raw = Tree(name="tree")
    handler = provider.wrap(raw)
    entered, release = threading.Event(), threading.Event()
    blocker = provider.events.submit(lambda: (entered.set(), release.wait(2)))
    assert entered.wait(2)
    events = []
    subscription = handler.subscribe(events.append)
    original = messages.FileMessage(
        file_path="first.h5", done=True, successful=True, metadata={"nested": {"value": 1}}
    )
    raw.file.put(msg=original)
    original.file_path = "second.h5"
    original.device_name = "another_detector"
    original.metadata["nested"]["value"] = 99
    release.set()
    blocker.result(2)
    subscription.close()
    event = next(event for event in events if event.channel == MessageChannel.FILE)
    assert event.message.file_path == "first.h5"
    assert event.message.device_name == "tree"
    assert event.message.metadata["nested"]["value"] == 1


def test_accepted_message_failure_is_observable_on_disposal(provider):
    raw = Tree(name="tree")
    handler = provider.wrap(raw)

    def failed(event):
        if event.channel == MessageChannel.FILE:
            raise RuntimeError("publication failed")

    subscription = handler.subscribe(failed)
    raw.file.put(file_path="file.h5", done=True, successful=True)
    with pytest.raises(RuntimeError, match="publication failed"):
        subscription.close()


def test_late_subscription_registration_releases_producer():
    with ThreadPoolExecutor(max_workers=1) as executor:
        subscription = EventSubscription(executor, lambda event: None)
        subscription.close()
        released = []
        with pytest.raises(RuntimeError, match="disposal"):
            subscription.own(lambda: released.append(True))
        assert released == [True]


def test_close_fences_new_device_admission(provider):
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()

    class GatedDevice(Device):
        def destroy(self):
            entered.set()
            assert release.wait(2)
            super().destroy()

    provider.wrap(GatedDevice(name="first"))
    closer = threading.Thread(target=lambda: (provider.close(), closed.set()))
    closer.start()
    try:
        assert entered.wait(2)
        with pytest.raises(RuntimeError, match="closing"):
            provider.wrap(Device(name="late"))
        release.set()
        assert closed.wait(2)
    finally:
        release.set()
        closer.join(2)


def test_read_generated_notifications_do_not_create_a_feedback_loop(provider):
    class PushOnRead(Signal):
        def get(self, **kwargs):
            self._run_subs(sub_type=self.SUB_VALUE, value=self._readback)
            return super().get(**kwargs)

    raw = PushOnRead(name="computed", value=0)
    handler = provider.wrap(raw)
    received = []
    completed = threading.Event()

    def callback(event):
        if event.value == 1:
            handler.read()
            received.append(event.value)
            completed.set()

    subscription = handler.subscribe_readback(callback)
    raw.put(1)
    assert completed.wait(2)
    provider.events.submit(lambda: None).result(2)
    subscription.close()
    assert received == [1]


def test_terminal_operation_still_notifies_late_observers_after_close(provider):
    handler = provider.wrap(Device(name="late"))
    native = StatusBase()
    operation = handler.operation(native)
    provider.close()
    observed = []
    operation.add_callback(lambda result: observed.append(result.exception()))
    assert len(observed) == 1
    assert isinstance(observed[0], DeviceClosedError)


def test_tree_close_fences_late_child_resolution_and_binding(provider):
    entered, release = threading.Event(), threading.Event()

    class GatedTree(Tree):
        def destroy(self):
            entered.set()
            assert release.wait(2)
            super().destroy()

    raw = GatedTree(name="tree")
    handler = provider.wrap(raw)
    errors = []

    def close():
        try:
            handler.close()
        except Exception as error:
            errors.append(error)

    closer = threading.Thread(target=close)
    closer.start()
    try:
        assert entered.wait(2)
        with pytest.raises(DeviceClosedError, match="closing"):
            handler.resolve("value")
        with pytest.raises(DeviceClosedError, match="closing"):
            provider.wrap(raw.file)
    finally:
        release.set()
        closer.join(2)
    assert not closer.is_alive()
    assert not errors
    assert not provider._handlers


def test_bounded_event_drain_preserves_ownership_for_retry(provider, monkeypatch):
    raw = Tree(name="tree")
    handler = provider.wrap(raw)
    entered, release = threading.Event(), threading.Event()
    child = handler.resolve("value")
    subscription = child.subscribe_readback(lambda event: (entered.set(), release.wait(2)))
    raw.value.put(1)
    assert entered.wait(2)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(subscription._condition, "wait_for", lambda *args, **kwargs: False)
            with pytest.raises(TimeoutError, match="draining"):
                provider.close()
        assert not provider._closed
        assert id(raw) in provider._handlers
        assert subscription in child._subscriptions
    finally:
        release.set()
    provider.close()
    assert provider._closed
    assert not provider._handlers


@pytest.mark.parametrize("dispose_during_destroy", [False, True])
def test_failed_destroy_keeps_original_subscription_token(provider, dispose_during_destroy):
    entered, release = threading.Event(), threading.Event()

    class FailsOnce(Tree):
        fail = True

        def destroy(self):
            if self.fail:
                entered.set()
                assert release.wait(2)
                raise RuntimeError("destroy failed")
            super().destroy()

    raw = FailsOnce(name="tree")
    root = provider.wrap(raw)
    child = root.resolve("value")
    observed = []
    token = child.subscribe_readback(observed.append)
    errors = []

    def close():
        try:
            root.close()
        except Exception as error:
            errors.append(error)

    closer = threading.Thread(target=close)
    closer.start()
    try:
        assert entered.wait(2)
        if dispose_during_destroy:
            token.close()
    finally:
        release.set()
        closer.join(2)
    assert len(errors) == 1
    assert "destroy failed" in str(errors[0])
    if not dispose_during_destroy:
        assert child._subscriptions == [token]
        raw.value.put(1)
        provider.events.submit(lambda: None).result(2)
        assert any(event.value == 1 for event in observed)
    token.close()
    previous = len(observed)
    raw.value.put(2)
    provider.events.submit(lambda: None).result(2)
    assert len(observed) == previous
    assert child._subscriptions == []
    raw.fail = False
    root.close()


def test_stop_is_not_blocked_by_native_rpc_waiting_for_transport(provider):
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()

    class BlockingDevice(Device):
        def trigger(self):
            self.pending = StatusBase()
            return self.pending

        def wait_for_stop(self):
            entered.set()
            assert release.wait(2)

        def stop(self, *, success=False):
            # Native status notification must also remain runnable during the RPC.
            self.pending.set_finished()
            release.set()

    raw = BlockingDevice(name="detector")
    handler = provider.wrap(raw)
    operation = handler.trigger()
    errors = []

    def rpc():
        try:
            handler.rpc("wait_for_stop", (), {})
        except Exception as error:
            errors.append(error)

    caller = threading.Thread(target=rpc)
    caller.start()
    assert entered.wait(2)
    stopper = threading.Thread(target=lambda: (handler.stop(), stopped.set()))
    stopper.start()
    try:
        assert stopped.wait(1), "Stop was queued behind a transport wait"
        operation.result(1)
    finally:
        release.set()
        caller.join(2)
        stopper.join(2)
    assert not errors


def test_failed_native_unsubscribe_remains_owned_until_successful_retry():
    with ThreadPoolExecutor(max_workers=1) as executor:
        subscription = EventSubscription(executor, lambda event: None)
        registered = [True]
        attempts = []

        def unsubscribe():
            attempts.append(True)
            if len(attempts) == 1:
                raise RuntimeError("native cleanup failed")
            registered.clear()

        subscription.own(unsubscribe)
        disposed = []
        subscription.on_close = lambda: disposed.append(True)
        with pytest.raises(RuntimeError, match="native cleanup failed"):
            subscription.close()
        assert registered
        assert not disposed
        subscription.close()
        assert not registered
        assert disposed == [True]
        assert len(attempts) == 2


def test_provider_close_accounts_for_inflight_constructor_and_rejects_new_ones(provider):
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    created = []

    class GatedConstructor(Device):
        def __init__(self, **kwargs):
            entered.set()
            assert release.wait(2)
            super().__init__(**kwargs)
            created.append(self)

    constructor = threading.Thread(
        target=lambda: provider.construct(GatedConstructor, {"name": "new"})
    )
    constructor.start()
    assert entered.wait(2)
    closer = threading.Thread(target=lambda: (provider.close(), closed.set()))
    closer.start()
    try:
        assert not closed.wait(0.05)
    finally:
        release.set()
        constructor.join(2)
        closer.join(2)
    assert closed.is_set()
    assert len(created) == 1
    assert created[0]._destroyed
    with pytest.raises(DeviceClosedError, match="closing"):
        provider.construct(GatedConstructor, {"name": "late"})
    assert len(created) == 1


def test_configuring_limits_does_not_require_prewrite_reads(provider):
    class WriteOnlyLimit(Signal):
        def get(self, **kwargs):
            raise RuntimeError("read unavailable")

        def set(self, value, **kwargs):
            self.written = value
            status = StatusBase()
            status.set_finished()
            return status

    class Limited(Device):
        low_limit_travel = Cpt(WriteOnlyLimit)
        high_limit_travel = Cpt(WriteOnlyLimit)

    raw = Limited(name="motor")
    provider.wrap(raw).configure({"limits": [-1, 2]})
    assert raw.low_limit_travel.written == -1
    assert raw.high_limit_travel.written == 2


def test_failed_set_submission_stops_partially_started_native_hardware(provider):
    error = RuntimeError("response lost after hardware started")

    class PartialSet(Signal):
        running = False
        stopped = False
        stop_done = threading.Event()

        def set(self, value, **kwargs):
            self.running = True
            raise error

        def stop(self, **kwargs):
            self.running = False
            self.stopped = True
            self.stop_done.set()

    raw = PartialSet(name="motor")
    with pytest.raises(RuntimeError) as failure:
        provider.wrap(raw).set(1)
    assert failure.value is error
    assert raw.stop_done.wait(2)
    assert raw.stopped
    assert not raw.running


def test_batched_array_invalidation_does_not_copy_or_retain_native_buffer(provider):
    import numpy as np

    copies = []

    class TrackedArray(np.ndarray):
        def __deepcopy__(self, memo):
            copies.append(self.nbytes)
            return np.array(self)

    class Waveform(Device):
        data = Cpt(Signal, value=0)

    raw = Waveform(name="waveform")
    raw.data._auto_monitor = True
    events = []
    provider.wrap(raw).subscribe(events.append)
    raw.data.put(np.arange(10000).view(TrackedArray))
    provider.events.submit(lambda: None).result(2)
    assert copies == []
    assert events[-1].kind == EventKind.READBACK
    assert events[-1].value is None


def test_legacy_value_conversion_has_no_provider_or_logging_side_effects():
    import logging
    from types import SimpleNamespace

    from ophyd_devices.bec_adapters import convert_value

    logger = logging.getLogger("ophyd")
    original = list(logger.handlers)
    marker = logging.NullHandler()
    logger.addHandler(marker)
    try:
        assert convert_value(SimpleNamespace(enum_strs=("off", "on"), name="choice"), 1.0) == 1
        assert marker in logger.handlers
    finally:
        logger.handlers[:] = original


def test_flush_reports_only_this_tree_new_errors_and_cannot_wait_on_event_owner(provider):
    first, second = [provider.wrap(Tree(name=name)) for name in ("first", "second")]

    def failed(event):
        if event.kind == EventKind.MESSAGE:
            raise RuntimeError("file publication failed")

    token = first.subscribe(failed)
    first.device.file.put(file_path="file.h5", done=True, successful=True)
    second.flush_events(2)
    with pytest.raises(RuntimeError, match="file publication failed"):
        first.flush_events(2)
    first.flush_events(2)  # An acknowledged old failure must not poison later requests.
    future = provider.events.submit(first.flush_events, 0.1)
    with pytest.raises(RuntimeError, match="own worker"):
        future.result(2)
    # Disposal retains the original accepted-message failure accounting.
    with pytest.raises(RuntimeError, match="file publication failed"):
        token.close()


def test_read_generated_peer_notifications_do_not_feed_back_across_roots(provider):
    class PeerSignal(Signal):
        peer = None

        def get(self, **kwargs):
            if self.peer is not None:
                self.peer._run_subs(sub_type=self.peer.SUB_VALUE, value=self._readback)
            return super().get(**kwargs)

    first, second = PeerSignal(name="first", value=0), PeerSignal(name="second", value=0)
    first.peer, second.peer = second, first
    handlers = {raw.name: provider.wrap(raw) for raw in (first, second)}
    received = []
    done = threading.Event()

    def callback(event):
        received.append(event.source.root)
        if len(received) < 10:
            handlers[event.source.root].read()
        done.set()

    tokens = [handler.subscribe_readback(callback) for handler in handlers.values()]
    # Discard initial run=True subscriptions before exercising a producer update.
    provider.events.submit(lambda: None).result(2)
    received.clear()
    first.put(1)
    assert done.wait(2)
    for token in tokens:
        token.close()
    assert received == ["first", "second"]


def test_failed_set_does_not_wait_for_native_failure_stop(provider):
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()

    class PartialSet(Signal):
        def set(self, value, **kwargs):
            raise ValueError("submission failed")

        def stop(self, **kwargs):
            entered.set()
            assert release.wait(2)
            stopped.set()

    raw = PartialSet(name="motor")
    try:
        with pytest.raises(ValueError, match="submission failed"):
            provider.wrap(raw).set(1)
        assert entered.wait(2)
        assert not stopped.is_set()
    finally:
        release.set()
    assert stopped.wait(2)


def test_idle_tree_fence_does_not_wait_for_an_unrelated_blocked_callback(provider):
    first, second = [provider.wrap(Tree(name=name)) for name in ("first", "second")]
    first.subscribe(lambda event: None)
    entered, release = threading.Event(), threading.Event()
    second.subscribe(lambda event: (entered.set(), release.wait(2)))
    second.device.file.put(file_path="second.h5", done=True, successful=True)
    assert entered.wait(2)
    try:
        first.flush_events(0.03)
    finally:
        release.set()


def test_acknowledged_delivery_failures_release_payloads_and_keep_bounded_summary():
    import numpy as np
    from bec_lib.device_backend import DeviceEvent, DeviceIdentity, EventKind, MessageChannel

    with ThreadPoolExecutor(max_workers=1) as executor:

        def failed(event):
            raise RuntimeError("publication unavailable")

        token = EventSubscription(executor, failed)
        references = []
        for index in range(3):
            message = messages.DevicePreviewMessage(
                data=np.arange(100000), signal="preview", device="detector"
            )
            references.append(weakref.ref(message.data))
            token.emit(
                DeviceEvent(
                    DeviceIdentity("detector"),
                    EventKind.MESSAGE,
                    message=message,
                    channel=MessageChannel.PREVIEW,
                )
            )
        del message
        token.wait_for_fence(token.fence(), 2)
        assert len(token.take_delivery_errors()) == 1
        executor.submit(lambda: None).result(2)  # The last delivery frame has returned.
        gc.collect()
        assert all(reference() is None for reference in references)
        assert len(token._errors) == 1
        assert token._failure_count == 3
        with pytest.raises(RuntimeError, match="publication unavailable"):
            token.close()


def test_first_changed_peer_is_published_with_causal_feedback_guard(provider):
    from ophyd_devices import ComputedSignal
    from ophyd_devices.sim.sim_signals import SetableSignal

    peer = SetableSignal(name="peer", value=0)
    computed = ComputedSignal(name="computed")
    computed.input_signals = [peer]
    computed.compute_method = "def compute(signal): return signal.get()"
    events = []
    token = provider.wrap(peer).subscribe_readback(events.append)
    provider.events.submit(lambda: None).result(2)
    events.clear()
    peer._value = 5
    provider.wrap(computed).read()
    token.wait_for_fence(token.fence(), 2)
    assert [event.value for event in events] == [5]
    token.close()


def test_tree_close_drains_owned_failed_submission_recovery(provider):
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()

    class PartialSet(Signal):
        def set(self, value, **kwargs):
            raise ValueError("submission failed")

        def stop(self, **kwargs):
            entered.set()
            assert release.wait(2)

    handler = provider.wrap(PartialSet(name="motor"))
    with pytest.raises(ValueError, match="submission failed"):
        handler.set(1)
    assert entered.wait(2)
    closer = threading.Thread(target=lambda: (handler.close(), closed.set()))
    closer.start()
    try:
        assert not closed.wait(0.05)
        release.set()
        assert closed.wait(2)
    finally:
        release.set()
        closer.join(2)
    assert handler._closed


def test_acknowledging_an_old_fence_preserves_later_delivery_failures():
    with ThreadPoolExecutor(max_workers=1) as executor:

        def failed(event):
            raise RuntimeError(str(event.value))

        token = EventSubscription(executor, failed)
        token.emit(DeviceEvent(DeviceIdentity("device"), EventKind.READBACK, value="first"))
        first = token.fence()
        token.emit(DeviceEvent(DeviceIdentity("device"), EventKind.READBACK, value="second"))
        second = token.fence()
        token.wait_for_fence(second, 2)
        assert "first" in str(token.take_delivery_errors(first)[0])
        assert "second" in str(token.take_delivery_errors(second)[0])
        assert token._failures.first is None
        assert token.take_delivery_errors(second) == []
        with pytest.raises(RuntimeError, match="first"):
            token.close()


def test_idle_failed_publication_keeps_bounded_accounting_without_completions(monkeypatch):
    from bec_lib.logger import bec_logger

    monkeypatch.setattr(bec_logger.logger, "error", lambda *args, **kwargs: None)
    with ThreadPoolExecutor(max_workers=1) as executor:

        def failed(event):
            raise RuntimeError("publication unavailable")

        token = EventSubscription(executor, failed)
        for _ in range(2000):
            token.emit(DeviceEvent(DeviceIdentity("device"), EventKind.READBACK))
        fence = token.fence()
        token.wait_for_fence(fence, 2)
        assert token._failure_count == 2000
        assert len(token._errors) == 1
        assert token._failures.first is not None
        assert token._failures.last is not None
        assert len(token._fences) == 1
        assert len(token.take_delivery_errors(fence)) == 1
        assert token._failures.first is None
        del fence
        gc.collect()
        assert not token._fences
        with pytest.raises(RuntimeError, match="publication unavailable"):
            token.close()


def test_recovery_fences_new_tree_commands_but_allows_reads_and_observation(provider):
    from ophyd_devices.bec_adapters.ophyd import DeviceRecoveryError

    entered, release = threading.Event(), threading.Event()

    class PartialSet(Signal):
        def set(self, value, **kwargs):
            if value == 0:
                raise ValueError("submission failed")
            return super().set(value, **kwargs)

        def stop(self, **kwargs):
            entered.set()
            assert release.wait(2)

    class RecoveringTree(Device):
        target = Cpt(PartialSet, value=0)
        peer = Cpt(Signal, value=0)

    root = provider.wrap(RecoveringTree(name="tree"))
    target = root.resolve("target")
    with pytest.raises(ValueError, match="submission failed"):
        target.set(0)
    assert entered.wait(2)
    try:
        with pytest.raises(DeviceRecoveryError, match="retry"):
            target.set(1)
        with pytest.raises(DeviceRecoveryError):
            root.resolve("peer").set(2)
        with pytest.raises(DeviceRecoveryError):
            root.trigger()
        assert root.read()["tree_target"]["value"] == 0
        token = target.subscribe_readback(lambda event: None)
        token.close()
        independent = provider.wrap(Signal(name="other", value=0))
        independent.set(3).result(2)
        assert independent.read()["other"]["value"] == 3
    finally:
        release.set()
    with root._idle:
        assert root._idle.wait_for(lambda: root._recovering == 0, 2)
    target.set(1).result(2)


def test_failed_recovery_submission_preserves_original_error_and_releases_admission(
    provider, monkeypatch
):
    class PartialSet(Signal):
        def set(self, value, **kwargs):
            raise ValueError("original submission failure")

    handler = provider.wrap(PartialSet(name="motor"))

    def rejected(*args, **kwargs):
        raise RuntimeError("executor unavailable")

    monkeypatch.setattr(provider.recovery, "submit", rejected)
    with pytest.raises(ValueError, match="original submission failure") as caught:
        handler.set(1)
    assert "executor unavailable" in caught.value.__notes__[0]
    assert handler._inflight == 0
    assert handler._recovering == 0


def test_tree_native_unsubscribe_failure_keeps_live_ownership_for_retry(provider, monkeypatch):
    raw = Tree(name="tree")
    handler = provider.wrap(raw)
    token = handler.subscribe(lambda event: None)
    provider.events.submit(lambda: None).result(2)
    original = raw.file.clear_sub

    def rejected(*args, **kwargs):
        raise RuntimeError("native removal failed")

    monkeypatch.setattr(raw.file, "clear_sub", rejected)
    with pytest.raises(RuntimeError, match="native removal failed"):
        handler.close()
    assert not raw._destroyed
    assert not handler._closed
    assert provider._handlers[id(raw)] is handler
    assert token in handler._subscriptions
    monkeypatch.setattr(raw.file, "clear_sub", original)
    handler.close()
    assert raw._destroyed
    assert handler._closed
    assert not provider._handlers


def test_failed_provider_shutdown_keeps_global_command_fence(provider, monkeypatch):
    raw = Signal(name="signal", value=0)
    handler = provider.wrap(raw)
    handler.subscribe_readback(lambda event: None)
    provider.events.submit(lambda: None).result(2)
    original = raw.clear_sub

    def rejected(*args, **kwargs):
        raise RuntimeError("native removal failed")

    monkeypatch.setattr(raw, "clear_sub", rejected)
    try:
        with pytest.raises(RuntimeError, match="native removal failed"):
            provider.close()
        assert not raw._destroyed
        with pytest.raises(DeviceClosedError, match="closing"):
            handler.set(7)
        assert handler.read()["signal"]["value"] == 0
    finally:
        monkeypatch.setattr(raw, "clear_sub", original)
        provider.close()
    assert raw._destroyed
    assert provider._closed
