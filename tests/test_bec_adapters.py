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
