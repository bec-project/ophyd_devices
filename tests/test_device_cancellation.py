"""Device cancellation owns late work and preserves resources during asynchronous cleanup."""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from ophyd import Component, Device, Signal

from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.utils.psi_device_base_utils import (
    CompareStatus,
    DeviceCleanupBlockedError,
    SequenceStatus,
    StatusBase,
    SubscriptionStatus,
)


class ResourceDevice(PSIDeviceBase):
    """Acquisition and cleanup acknowledgements use distinct live signals."""

    value = Component(Signal, value=0)
    ready = Component(Signal, value=0)


def finish_for_cleanup(status):
    """Retire test-owned pending work even when the regression assertion fails."""
    if status is not None and not status.done:
        status.set_exception(RuntimeError("Test cleanup"))


@pytest.mark.parametrize("action", ["stop", "destroy"])
@pytest.mark.parametrize("sequence", [False, True], ids=["watcher", "sequence"])
def test_completion_callback_cannot_register_live_successor_during_cancellation(action, sequence):
    owner = ResourceDevice(name="owner")
    first = StatusBase()
    successor = []
    watchers = []

    def register_successor(_finished):
        watcher = CompareStatus(owner.value, 1, run=False)
        watchers.append(watcher)
        status = SequenceStatus(steps=[lambda: watcher]) if sequence else watcher
        successor.append(status)
        owner.cancel_on_stop(status)

    owner.cancel_on_stop(first)
    first.add_callback(register_successor)
    try:
        getattr(owner, action)()
        assert len(successor) == 1
        with pytest.raises(DeviceStoppedError):
            successor[0].wait(timeout=0.1)
        assert watchers[0].done
        assert not owner.value._callbacks[owner.value.SUB_VALUE]
        assert not owner._stoppable_status_objects
    finally:
        for status in successor:
            finish_for_cleanup(status)
        for watcher in watchers:
            finish_for_cleanup(watcher)
        owner.destroy()


def test_registration_during_stop_hook_is_cancelled_before_hook_finishes():
    owner = ResourceDevice(name="owner")
    entered, release = threading.Event(), threading.Event()
    successor = None

    def stop_hook():
        entered.set()
        assert release.wait(timeout=2)

    owner.on_stop = stop_hook
    with ThreadPoolExecutor(max_workers=1) as callers:
        stopped = callers.submit(owner.stop)
        try:
            assert entered.wait(timeout=1)
            assert not owner.stopped  # The stopping guard must cover the hook too.
            successor = SubscriptionStatus(owner.value, lambda **_: False, run=False)
            owner.cancel_on_stop(successor)
            with pytest.raises(DeviceStoppedError):
                successor.wait(timeout=0.1)
            assert not owner.value._callbacks[owner.value.SUB_VALUE]
        finally:
            release.set()
            stopped.result(timeout=1)
            finish_for_cleanup(successor)
            owner.destroy()


def test_registration_after_stop_is_immediately_cancelled():
    owner = ResourceDevice(name="owner")
    pending = None
    try:
        owner.stop()
        pending = CompareStatus(owner.value, 1, run=False)
        owner.cancel_on_stop(pending)
        with pytest.raises(DeviceStoppedError):
            pending.wait(timeout=0.1)
        assert not owner.value._callbacks[owner.value.SUB_VALUE]
        assert not owner._stoppable_status_objects
    finally:
        finish_for_cleanup(pending)
        owner.destroy()


def test_unstage_snapshot_preserves_work_created_by_its_hook():
    owner = ResourceDevice(name="owner")
    retiring = successor = None
    try:
        owner.stage()
        retiring = CompareStatus(owner.value, 1, run=False)
        owner.cancel_on_stop(retiring)

        def unstage_hook():
            nonlocal successor
            successor = CompareStatus(owner.ready, 1, run=False)
            owner.cancel_on_stop(successor)
            return successor

        owner.on_unstage = unstage_hook
        assert owner.unstage() is successor
        with pytest.raises(DeviceStoppedError):
            retiring.wait(timeout=0.1)
        assert not successor.done
        owner.ready.put(1)
        successor.wait(timeout=1)
        assert successor.success
    finally:
        finish_for_cleanup(retiring)
        finish_for_cleanup(successor)
        owner.destroy()


def test_new_stage_allows_registration_after_previous_scan_was_stopped():
    owner = ResourceDevice(name="owner")
    pending = None
    try:
        owner.stage()
        owner.stop()
        owner.unstage()
        owner.stage()
        assert not owner.stopped
        pending = CompareStatus(owner.value, 1, run=False)
        owner.cancel_on_stop(pending)
        assert not pending.done
        owner.value.put(1)
        pending.wait(timeout=1)
        assert pending.success
        owner.unstage()
    finally:
        finish_for_cleanup(pending)
        owner.destroy()


@pytest.mark.parametrize("composite", [False, True], ids=["sequence", "composite"])
@pytest.mark.parametrize("nested", [False, True], ids=["root", "ordinary_group"])
@pytest.mark.parametrize("stop_first", [False, True], ids=["destroy", "stop_then_destroy"])
def test_destroy_preserves_live_resources_until_sequence_cleanup_acknowledges(
    monkeypatch, nested, stop_first, composite
):
    class Group(Device):
        worker = Component(ResourceDevice)

    class Root(PSIDeviceBase):
        group = Component(Group)

    root = Root(name="root") if nested else ResourceDevice(name="root")
    owner = root.group.worker if nested else root
    started = threading.Event()
    cleanup_statuses = []
    cleanup_reads = []
    acquisition = CompareStatus(owner.value, 1, run=False)

    def cleanup(_error):
        acknowledgement = CompareStatus(owner.ready, 1, run=False)
        acknowledgement.add_callback(
            lambda _finished: cleanup_reads.append((owner.value._destroyed, owner.value.get()))
        )
        cleanup_statuses.append(acknowledgement)
        started.set()
        return acknowledgement

    sequence = SequenceStatus(steps=[lambda: acquisition], on_failure=cleanup)
    owned = sequence & StatusBase() if composite else sequence
    owner.cancel_on_stop(owned)
    shutdown = Mock(wraps=owner.task_handler.shutdown)
    monkeypatch.setattr(owner.task_handler, "shutdown", shutdown)
    try:
        if stop_first:
            owner.stop()
            assert started.wait(timeout=1)
            assert not sequence.done
            assert owned in owner._stoppable_status_objects
        with pytest.raises(DeviceCleanupBlockedError):
            root.destroy()
        assert started.wait(timeout=1)
        shutdown.assert_called_once()
        assert not root.destroyed
        assert not owner.destroyed
        assert not owner.value._destroyed
        assert not owner.ready._destroyed
        assert owner.ready._callbacks[owner.ready.SUB_VALUE]
        assert not sequence.done
        if nested:
            assert not root.group._destroyed

        owner.ready.put(1)
        with pytest.raises(DeviceStoppedError):
            owned.wait(timeout=1)
        assert sequence.done
        assert cleanup_reads == [(False, 0)]
        assert not owner.ready._callbacks[owner.ready.SUB_VALUE]
        root.destroy()
        assert root.destroyed
        assert owner.value._destroyed
        assert owner.ready._destroyed
        assert not owner._stoppable_status_objects
    finally:
        # Directly finish the acknowledgement even if old code destroyed its signal.
        for acknowledgement in cleanup_statuses:
            if not acknowledgement.done:
                acknowledgement.set_finished()
        finish_for_cleanup(owned)
        finish_for_cleanup(sequence)
        finish_for_cleanup(acquisition)
        root.destroy()


@pytest.mark.parametrize("watcher", [False, True], ids=["status", "compare_status"])
def test_destroy_allows_committed_native_cancellation_before_callbacks_finish(monkeypatch, watcher):
    """A pending native notification is not unfinished sequence-owned resource cleanup."""
    owner = ResourceDevice(name="owner")
    pending = (
        CompareStatus(owner.value, 1, run=False, timeout=60)
        if watcher
        else StatusBase(owner, timeout=60)
    )
    entered, release = threading.Event(), threading.Event()
    settled = pending._settled

    def delayed_notification():
        entered.set()
        assert release.wait(timeout=2)
        settled()

    # Hold the real callback thread before it sets the done event. This makes
    # the distinction between committed cancellation and notification deterministic.
    monkeypatch.setattr(pending, "_settled", delayed_notification)
    owner.cancel_on_stop(pending)
    try:
        owner.destroy()
        assert entered.wait(timeout=1)
        assert pending._externally_initiated_completion
        assert not pending.done
        assert owner.destroyed
        assert owner.value._destroyed
    finally:
        release.set()
        if not pending.done and not pending._externally_initiated_completion:
            pending.set_exception(RuntimeError("Test cleanup"))
        pending._callback_thread.join(timeout=1)
        owner.destroy()
    assert not pending._callback_thread.is_alive()
    with pytest.raises(DeviceStoppedError):
        pending.wait(timeout=1)
    assert not owner._stoppable_status_objects
