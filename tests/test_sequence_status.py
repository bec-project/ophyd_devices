"""
Sequential status operations retain ordering, cancellation ownership and failure cleanup.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from ophyd import Signal
from ophyd.status import StatusBase as NativeStatus

from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.utils.psi_device_base_utils import (
    AndStatus,
    DeviceStatus,
    ExceptionStatus,
    MoveStatus,
    SequenceStatus,
    Status,
    StatusBase,
    SubscriptionStatus,
    all_statuses,
)


def test_sequence_starts_only_after_previous_step_succeeds():
    events = []
    child = StatusBase()

    def first():
        events.append("first")

    def second():
        events.append("second")
        return child

    sequence = SequenceStatus(steps=[first, second, lambda: events.append("third")])
    assert events == ["first", "second"]
    assert not sequence.done
    child.set_finished()
    sequence.wait(timeout=1)
    assert events == ["first", "second", "third"]


@pytest.mark.parametrize("completed_child", [False, True])
def test_many_immediate_steps_do_not_recurse(completed_child):
    child = NativeStatus()
    child.set_finished()
    step = Mock(return_value=child if completed_child else None)
    sequence = SequenceStatus(steps=[step] * 2000)
    sequence.wait(timeout=1)
    assert step.call_count == 2000


def test_deferred_run_is_idempotent():
    step = Mock(return_value=None)
    sequence = SequenceStatus(steps=[step], run=False)
    assert not sequence.done
    step.assert_not_called()
    sequence.run()
    sequence.run()
    sequence.wait(timeout=1)
    step.assert_called_once()


@pytest.mark.parametrize("synchronous", [False, True])
def test_failure_preserves_error_and_does_not_start_later_steps(synchronous):
    original = RuntimeError("acquisition failed")
    child, later, cleanup = NativeStatus(), Mock(), Mock(return_value=None)

    def step():
        if synchronous:
            raise original
        return child

    sequence = SequenceStatus(steps=[step, later], on_failure=cleanup)
    if not synchronous:
        child.set_exception(original)
    with pytest.raises(RuntimeError, match="acquisition failed") as failure:
        sequence.wait(timeout=1)
    assert failure.value is original
    cleanup.assert_called_once_with(original)
    later.assert_not_called()


def test_async_failure_cleanup_finishes_before_failure_is_reported():
    child, cleanup_done = StatusBase(), StatusBase()
    original = RuntimeError("original")
    cleanup = Mock(return_value=cleanup_done)
    sequence = SequenceStatus(steps=[lambda: child], on_failure=cleanup)
    child.set_exception(original)
    cleanup.assert_called_once_with(original)
    assert not sequence.done
    sequence.set_exception(RuntimeError("later cancellation"))
    assert not sequence.done
    cleanup_done.set_finished()
    with pytest.raises(RuntimeError, match="original") as failure:
        sequence.wait(timeout=1)
    assert failure.value is original


@pytest.mark.parametrize("asynchronous", [False, True])
def test_cleanup_failure_does_not_replace_original_error(asynchronous):
    original, cleanup_error = RuntimeError("original"), RuntimeError("cleanup failed")
    cleanup_status = StatusBase()

    def cleanup(error):
        assert error is original
        if not asynchronous:
            raise cleanup_error
        return cleanup_status

    sequence = SequenceStatus(steps=[], on_failure=cleanup, run=False)
    sequence.set_exception(original)
    if asynchronous:
        cleanup_status.set_exception(cleanup_error)
    with pytest.raises(RuntimeError, match="original") as failure:
        sequence.wait(timeout=1)
    assert failure.value is original
    assert "cleanup failed" in " ".join(original.__notes__)


def test_cancel_pending_step_releases_owned_subscriptions():
    signal, children = Signal(name="value", value=0), []
    later = Mock()

    def step():
        child = SubscriptionStatus(signal, lambda *, value, **_: value == 1, run=False)
        children.append(child)
        return child

    sequence = SequenceStatus(steps=[step, later])
    original = RuntimeError("cancelled")
    sequence.set_exception(original)
    with pytest.raises(RuntimeError, match="cancelled"):
        sequence.wait(timeout=1)
    assert children[0].done
    assert not signal._callbacks[signal.SUB_VALUE]
    later.assert_not_called()
    signal.destroy()


def test_cancel_during_step_startup_waits_for_result_and_cleans_it():
    entered, release = threading.Event(), threading.Event()
    signal = Signal(name="value", value=0)
    children, cleanup_events = [], []
    later = Mock()

    def step():
        child = SubscriptionStatus(signal, lambda *, value, **_: value == 1, run=False)
        children.append(child)
        entered.set()
        assert release.wait(timeout=2)
        return child

    sequence = SequenceStatus(
        steps=[step, later], on_failure=lambda error: cleanup_events.append(error), run=False
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        started = pool.submit(sequence.run)
        assert entered.wait(timeout=1)
        try:
            sequence.set_exception(RuntimeError("cancelled during startup"))
            assert not sequence.done
            assert not cleanup_events
        finally:
            release.set()
        started.result(timeout=1)
    with pytest.raises(RuntimeError, match="cancelled during startup"):
        sequence.wait(timeout=1)
    assert children[0].done
    assert not signal._callbacks[signal.SUB_VALUE]
    assert len(cleanup_events) == 1
    later.assert_not_called()
    signal.destroy()


def test_cancel_before_run_never_starts_operations():
    step, cleanup = Mock(), Mock(return_value=None)
    sequence = SequenceStatus(steps=[step], on_failure=cleanup, run=False)
    original = RuntimeError("stopped before run")
    sequence.set_exception(original)
    sequence.run()
    with pytest.raises(RuntimeError, match="stopped before run"):
        sequence.wait(timeout=1)
    step.assert_not_called()
    cleanup.assert_called_once_with(original)


def test_reentrant_cancellation_runs_cleanup_once():
    calls = []

    def cleanup(error):
        calls.append(error)
        sequence.set_exception(RuntimeError("stop callback"))

    sequence = SequenceStatus(steps=[], on_failure=cleanup, run=False)
    original = RuntimeError("first")
    sequence.set_exception(original)
    with pytest.raises(RuntimeError, match="first"):
        sequence.wait(timeout=1)
    assert calls == [original]


def test_parent_cancellation_waits_for_nested_sequence_cleanup():
    cleanup = StatusBase()
    events = []
    child = SequenceStatus(
        steps=[lambda: StatusBase()],
        on_failure=lambda error: (events.append("child cleanup"), cleanup)[1],
    )
    parent = SequenceStatus(
        steps=[lambda: child], on_failure=lambda error: events.append("parent cleanup")
    )
    parent.set_exception(RuntimeError("parent cancelled"))
    assert events == ["child cleanup"]
    assert not parent.done
    cleanup.set_finished()
    with pytest.raises(RuntimeError, match="parent cancelled"):
        parent.wait(timeout=1)
    assert child.done
    assert events == ["child cleanup", "parent cleanup"]


def test_composite_cancellation_releases_all_owned_children():
    first, second = Signal(name="first", value=0), Signal(name="second", value=0)
    waiting = SubscriptionStatus(first, lambda *, value, **_: value == 1, run=False)
    watching = ExceptionStatus(second, 1, exception=RuntimeError("failed"))
    sequence = SequenceStatus(steps=[lambda: all_statuses((waiting, watching))])
    sequence.set_exception(RuntimeError("cancelled"))
    with pytest.raises(RuntimeError, match="cancelled"):
        sequence.wait(timeout=1)
    assert not first._callbacks[first.SUB_VALUE]
    assert not second._callbacks[second.SUB_VALUE]
    assert waiting.done
    assert watching.done
    first.destroy()
    second.destroy()


@pytest.mark.parametrize("invalid", [[StatusBase()], [None], [42]])
def test_constructor_rejects_already_created_statuses_and_noncallables(invalid):
    with pytest.raises(TypeError, match="steps must be callables"):
        SequenceStatus(steps=invalid)


def test_invalid_step_result_fails_and_runs_cleanup():
    cleanup = Mock(return_value=None)
    sequence = SequenceStatus(steps=[lambda: 123], on_failure=cleanup)
    with pytest.raises(TypeError, match="return a status or None"):
        sequence.wait(timeout=1)
    cleanup.assert_called_once()


def test_empty_sequence_succeeds_and_later_cancellation_cannot_change_it():
    sequence = SequenceStatus(steps=[])
    sequence.wait(timeout=1)
    sequence.set_exception(RuntimeError("too late"))
    assert sequence.success


def test_sequence_cannot_be_marked_successful_externally():
    sequence = SequenceStatus(steps=[lambda: StatusBase()], run=False)
    with pytest.raises(RuntimeError, match="only after all"):
        sequence.set_finished()
    sequence.set_exception(RuntimeError("test cleanup"))


def test_all_statuses_empty_singleton_and_child_failure():
    assert all_statuses([]).success
    first, second = StatusBase(), StatusBase()
    assert all_statuses([first]) is first
    both = all_statuses([first, second])
    first.set_finished()
    assert not both.done
    second.set_exception(RuntimeError("failed child"))
    with pytest.raises(RuntimeError, match="failed child"):
        both.wait(timeout=1)


@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_composite_keeps_first_roi_sequence_failure_when_canceling_other_rois(failed_index):
    """
    Combining several ROI-style sequences must retain the error before sibling cleanup.
    """
    signals = [Signal(name=f"roi_{index}", value=0) for index in range(3)]
    sequences = [
        SequenceStatus(
            steps=[lambda signal=signal: SubscriptionStatus(signal, lambda **_: False, run=False)]
        )
        for signal in signals
    ]
    combined = all_statuses(sequences)
    original = RuntimeError("ROI arming command failed")
    try:
        sequences[failed_index].set_exception(original)
        with pytest.raises(RuntimeError, match="ROI arming command failed") as caught:
            combined.wait(timeout=1)
        assert caught.value is original
        assert all(sequence.done for sequence in sequences)
        assert all(not signal._callbacks[signal.SUB_VALUE] for signal in signals)
    finally:
        for signal in signals:
            signal.destroy()


@pytest.mark.parametrize("stop_from", ["failing_sequence", "sibling_cleanup"])
def test_composite_failure_survives_reentrant_device_stop(stop_from):
    """
    Device stop during sequence cleanup cannot replace an already committed child error.
    """
    owner = PSIDeviceBase(name="status_owner")
    first = SequenceStatus(
        steps=[lambda: StatusBase()],
        on_failure=(lambda error: owner.stop()) if stop_from == "failing_sequence" else None,
    )
    second = SequenceStatus(
        steps=[lambda: StatusBase()],
        on_failure=(lambda error: owner.stop()) if stop_from == "sibling_cleanup" else None,
    )
    combined = first & second
    for status in (first, second, combined):
        owner.cancel_on_stop(status)
    original = RuntimeError("original ROI failure")
    try:
        first.set_exception(original)
        with pytest.raises(RuntimeError, match="original ROI failure") as caught:
            combined.wait(timeout=1)
        assert caught.value is original
        assert owner.stopped
        assert first.done and second.done
    finally:
        owner.destroy()


def test_composite_waits_for_cancelled_sibling_sequence_cleanup():
    """
    Report the original error only after asynchronous sibling cleanup has finished.
    """
    cleanup_finished = StatusBase()
    events = []
    first = SequenceStatus(steps=[lambda: StatusBase()])
    second = SequenceStatus(
        steps=[lambda: StatusBase()],
        on_failure=lambda error: (events.append("cleanup started"), cleanup_finished)[1],
    )
    combined = first & second
    combined.add_callback(lambda status: events.append("composite finished"))
    original = RuntimeError("first sequence failed")
    first.set_exception(original)
    assert events == ["cleanup started"]
    assert not combined.done
    cleanup_finished.set_finished()
    with pytest.raises(RuntimeError, match="first sequence failed") as caught:
        combined.wait(timeout=1)
    assert caught.value is original
    assert second.done
    assert events == ["cleanup started", "composite finished"]


def test_external_composite_cancellation_waits_for_nested_cleanup():
    """
    Direct owner cancellation also releases subscriptions before completing the composite.
    """
    signal = Signal(name="cancelled", value=0)
    watcher = SubscriptionStatus(signal, lambda **_: False, run=False)
    cleanup_finished = StatusBase()
    nested = SequenceStatus(steps=[lambda: watcher], on_failure=lambda error: cleanup_finished)
    combined = AndStatus(StatusBase(), nested)
    original = DeviceStoppedError("owner stopped")
    try:
        combined.set_exception(original)
        assert not signal._callbacks[signal.SUB_VALUE]
        assert not combined.done
        combined.set_exception(RuntimeError("reentrant cancellation"))
        cleanup_finished.set_finished()
        with pytest.raises(DeviceStoppedError, match="owner stopped") as caught:
            combined.wait(timeout=1)
        assert caught.value is original
        assert nested.done
    finally:
        signal.destroy()


def test_composite_failure_callbacks_run_without_holding_its_bookkeeping_lock():
    """
    A completion callback can wait for another thread to access the same composite.
    """
    first = SequenceStatus(steps=[lambda: StatusBase()])
    second = SequenceStatus(steps=[lambda: StatusBase()])
    combined = first & second
    callback_finished = threading.Event()
    callback_errors = []
    original = RuntimeError("original composite failure")
    with ThreadPoolExecutor(max_workers=1) as pool:

        def completed(status):
            try:
                pool.submit(combined.set_exception, RuntimeError("late stop")).result(timeout=1)
            except Exception as error:
                callback_errors.append(error)
            finally:
                callback_finished.set()

        combined.add_callback(completed)
        first.set_exception(original)
        with pytest.raises(RuntimeError, match="original composite failure") as caught:
            combined.wait(timeout=1)
        assert callback_finished.wait(timeout=1)
        assert not callback_errors
        assert caught.value is original


def test_committed_failure_watch_error_wins_before_its_callback_runs(monkeypatch):
    """
    A pending failure callback must not let the primary status acknowledge success.
    """
    signal = Signal(name="failure_watch", value=0)
    original = RuntimeError("detector failed")
    watching = ExceptionStatus(signal, 1, exception=original, run=False)
    primary = StatusBase()
    combined = primary & watching
    finish_failure = watching._run_callbacks
    monkeypatch.setattr(watching, "_run_callbacks", Mock())
    try:
        signal.put(1)
        assert not watching.done
        primary.set_finished()
        with pytest.raises(RuntimeError, match="detector failed") as caught:
            combined.wait(timeout=1)
        assert caught.value is original
        assert not signal._callbacks[signal.SUB_VALUE]
    finally:
        finish_failure()
        signal.destroy()


@pytest.mark.parametrize("asynchronous_cleanup", [False, True])
def test_sequence_cleans_children_of_constructor_timed_out_composite(asynchronous_cleanup):
    """
    Native composite timeouts still require the parent to release and settle owned children.
    """
    signal = Signal(name="timed_out_composite", value=0)
    watcher = SubscriptionStatus(signal, lambda **_: False, run=False)
    cleanup_started = threading.Event()
    cleanup_finished = StatusBase()

    def cleanup(error):
        cleanup_started.set()
        return cleanup_finished if asynchronous_cleanup else None

    nested = SequenceStatus(steps=[lambda: StatusBase()], on_failure=cleanup)
    combined = AndStatus(watcher, nested, timeout=0.01)
    parent = SequenceStatus(steps=[lambda: combined])
    try:
        assert cleanup_started.wait(timeout=1)
        assert watcher.done
        assert not signal._callbacks[signal.SUB_VALUE]
        if asynchronous_cleanup:
            assert not parent.done
            cleanup_finished.set_finished()
        with pytest.raises(TimeoutError):
            parent.wait(timeout=1)
        assert nested.done
    finally:
        if not cleanup_finished.done:
            cleanup_finished.set_finished()
        signal.destroy()


@pytest.mark.parametrize("parent_kind", ["sequence", "composite"])
def test_composite_constructor_timeout_during_owned_cleanup_keeps_parent_waiting(parent_kind):
    """
    A native composite timeout cannot let its parent skip asynchronous sequence cleanup.
    """
    cleanup_finished = StatusBase()
    first = SequenceStatus(steps=[lambda: StatusBase()])
    second = SequenceStatus(steps=[lambda: StatusBase()], on_failure=lambda error: cleanup_finished)
    combined = AndStatus(first, second, timeout=0.01)
    parent = (
        SequenceStatus(steps=[lambda: combined])
        if parent_kind == "sequence"
        else combined & StatusBase()
    )
    parent_finished = threading.Event()
    parent.add_callback(lambda status: parent_finished.set())
    try:
        first.set_exception(RuntimeError("acquisition failed before composite timeout"))
        assert combined._event.wait(timeout=1)
        native_timeout = combined.exception(timeout=0)
        assert isinstance(native_timeout, TimeoutError)
        assert not parent_finished.wait(timeout=0.05)
        cleanup_finished.set_finished()
        with pytest.raises(TimeoutError) as caught:
            parent.wait(timeout=1)
        assert caught.value is native_timeout
        assert second.done
        assert combined.exception(timeout=0) is native_timeout
    finally:
        if not cleanup_finished.done:
            cleanup_finished.set_finished()


def test_composite_committed_constructor_timeout_survives_cleanup_before_done(monkeypatch):
    """
    Cleanup cannot overwrite a native timeout while its completion notification is delayed.
    """
    cleanup_finished = StatusBase()
    first = SequenceStatus(steps=[lambda: StatusBase()])
    second = SequenceStatus(steps=[lambda: StatusBase()], on_failure=lambda error: cleanup_finished)
    timeout_committed = threading.Event()
    notify_timeout = threading.Event()
    combined = AndStatus(first, second, timeout=0.05)

    def delayed_notification():
        timeout_committed.set()
        assert notify_timeout.wait(timeout=2)

    monkeypatch.setattr(combined, "_settled", delayed_notification)
    parent = SequenceStatus(steps=[lambda: combined])
    try:
        first.set_exception(RuntimeError("original acquisition failure"))
        assert timeout_committed.wait(timeout=1)
        native_timeout = combined._exception
        assert isinstance(native_timeout, TimeoutError)
        assert not combined.done
        assert not parent.done
        assert not second.done
        cleanup_finished.set_finished()
        assert second.done
        assert combined._exception is native_timeout
        notify_timeout.set()
        with pytest.raises(TimeoutError) as caught:
            parent.wait(timeout=1)
        assert caught.value is native_timeout
        assert combined.exception(timeout=0) is native_timeout
    finally:
        notify_timeout.set()
        if not cleanup_finished.done:
            cleanup_finished.set_finished()
        combined._callback_thread.join(timeout=1)


def test_synchronous_wait_timeout_is_reported_after_cleanup():
    from ophyd.utils.errors import WaitTimeoutError

    error = WaitTimeoutError("step timed out")
    cleanup = Mock(return_value=None)

    def step():
        raise error

    sequence = SequenceStatus(steps=[step], on_failure=cleanup)
    with pytest.raises(TimeoutError, match="step timed out") as caught:
        sequence.wait(timeout=1)
    assert caught.value.__cause__ is error
    cleanup.assert_called_once_with(error)


def test_failed_cleanup_composite_waits_for_nested_cleanup():
    cleanup_done, cleanup_fail = StatusBase(), StatusBase()
    nested = SequenceStatus(steps=[lambda: StatusBase()], on_failure=lambda error: cleanup_done)
    original = RuntimeError("original acquisition failure")

    def fail():
        raise original

    parent = SequenceStatus(
        steps=[fail], on_failure=lambda error: all_statuses([cleanup_fail, nested])
    )
    cleanup_fail.set_exception(RuntimeError("cleanup composite failed"))
    assert not parent.done
    assert not nested.done
    cleanup_done.set_finished()
    with pytest.raises(RuntimeError, match="original acquisition failure") as caught:
        parent.wait(timeout=1)
    assert caught.value is original
    assert nested.done
    assert "cleanup composite failed" in " ".join(original.__notes__)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_nested_cleanup_failure_is_retained_on_parent_error(asynchronous):
    cleanup_done = StatusBase()

    def cleanup(error):
        if asynchronous:
            return cleanup_done
        raise RuntimeError("hardware cleanup failed")

    nested = SequenceStatus(steps=[lambda: StatusBase()], on_failure=cleanup)
    parent = SequenceStatus(steps=[lambda: nested])
    original = RuntimeError("parent cancelled")
    parent.set_exception(original)
    if asynchronous:
        cleanup_done.set_exception(RuntimeError("hardware cleanup failed"))
    with pytest.raises(RuntimeError, match="parent cancelled") as caught:
        parent.wait(timeout=1)
    assert caught.value is original
    assert "hardware cleanup failed" in " ".join(original.__notes__)


def test_shared_nested_failure_does_not_copy_its_own_notes():
    original = RuntimeError("shared failure")
    original.add_note("existing detail")
    nested = SequenceStatus(steps=[lambda: StatusBase()])
    parent = SequenceStatus(steps=[lambda: nested])
    nested.set_exception(original)
    with pytest.raises(RuntimeError, match="shared failure") as caught:
        parent.wait(timeout=1)
    assert caught.value is original
    assert original.__notes__ == ["existing detail"]


def test_sequence_preserves_operation_context_across_callback_threads():
    from contextvars import ContextVar

    owner = ContextVar("owner", default=None)
    child, observed = StatusBase(), []
    token = owner.set("original")
    try:
        sequence = SequenceStatus(steps=[lambda: child, lambda: observed.append(owner.get())])
    finally:
        owner.reset(token)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(child.set_finished).result(timeout=1)
    sequence.wait(timeout=1)
    assert observed == ["original"]


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("composite", [False, True])
def test_sequence_keeps_committed_hardware_error_through_reentrant_stop(nested, composite):
    """
    Owner stop before a child's callbacks cannot replace its concrete hardware error.
    """
    owner = PSIDeviceBase(name="owner")
    child = DeviceStatus(owner)
    cleaned, later = [], Mock()
    active = SequenceStatus(steps=[lambda: child]) if nested else child
    sequence = SequenceStatus(
        steps=[lambda: active, later], on_failure=lambda error: cleaned.append(error)
    )
    result = sequence & StatusBase() if composite else sequence
    owner.cancel_on_stop(result)
    original = RuntimeError("hardware communication failed")
    try:
        child.set_exception(original)
        with pytest.raises(RuntimeError, match="hardware communication failed") as caught:
            result.wait(timeout=1)
        assert caught.value is original
        assert cleaned == [original]
        later.assert_not_called()
    finally:
        owner.destroy()


def test_subscription_timeout_during_registration_releases_late_watcher(monkeypatch):
    """
    A subscribe call returning after timeout cannot retain or invoke a dead watcher.
    """
    signal = Signal(name="late_registration", value=1)
    callback = Mock(return_value=True)
    subscribe = signal.subscribe

    def delayed(watcher, **kwargs):
        status = watcher.__self__
        assert status._event.wait(timeout=1)
        status._callback_thread.join(timeout=1)
        assert not status._callback_thread.is_alive()
        return subscribe(watcher, **kwargs)

    monkeypatch.setattr(signal, "subscribe", delayed)
    status = SubscriptionStatus(signal, callback, timeout=0.01)
    assert status.done
    assert not status.success
    assert not signal._callbacks[signal.SUB_VALUE]
    callback.assert_not_called()


def test_subscription_registration_failure_releases_partial_watcher(monkeypatch):
    """
    Failed setup does not retain a callback registered before subscribe raised.
    """
    signal = Signal(name="partial_registration", value=0)
    subscribe = signal.subscribe
    statuses = []
    failure = RuntimeError("subscription setup failed")

    def failing(watcher, **kwargs):
        statuses.append(watcher.__self__)
        subscribe(watcher, **kwargs)
        raise failure

    monkeypatch.setattr(signal, "subscribe", failing)
    with pytest.raises(RuntimeError, match="subscription setup failed"):
        SubscriptionStatus(signal, lambda **_: False, run=False, timeout=60)
    assert not signal._callbacks[signal.SUB_VALUE]
    status = statuses[0]
    status._callback_thread.join(timeout=1)
    assert not status._callback_thread.is_alive()
    assert status.exception(timeout=1) is failure


@pytest.mark.parametrize("status_class", [StatusBase, Status, DeviceStatus, MoveStatus])
def test_all_status_wrappers_preserve_committed_timeout(monkeypatch, status_class):
    """
    Late failure cannot replace timeout before or after its completion is announced.
    """
    from ophyd import SoftPositioner
    from ophyd.utils.errors import InvalidState

    entered, release = threading.Event(), threading.Event()
    original_settled = status_class._settled

    def delayed_settled(status):
        entered.set()
        assert release.wait(timeout=2)
        original_settled(status)

    monkeypatch.setattr(status_class, "_settled", delayed_settled)
    owner = PSIDeviceBase(name="owner")
    positioner = SoftPositioner(name="positioner", init_pos=0)
    if status_class is DeviceStatus:
        status = status_class(owner, timeout=0.02)
    elif status_class is MoveStatus:
        status = status_class(positioner, 1, timeout=0.02)
    else:
        status = status_class(timeout=0.02)
    try:
        assert entered.wait(timeout=1)
        original = status._exception
        assert original is not None
        with pytest.raises(InvalidState):
            status.set_exception(RuntimeError("late cancellation before callbacks"))
        assert status._exception is original
    finally:
        release.set()
    status._callback_thread.join(timeout=1)
    assert not status._callback_thread.is_alive()
    assert status.exception(timeout=1) is original
    with pytest.raises(InvalidState):
        status.set_exception(RuntimeError("late cancellation after callbacks"))
    assert status.exception(timeout=1) is original
    owner.destroy()
    positioner.destroy()


def test_large_status_collection_cancels_all_children_and_awaits_sequence_cleanup():
    """
    Large collections stay shallow and cannot abandon early children during cancellation.
    """
    child, cleanup = StatusBase(), StatusBase()
    sequence = SequenceStatus(steps=[lambda: child], on_failure=lambda error: cleanup)
    leaves = [sequence, *(StatusBase() for _ in range(1000))]
    combined = all_statuses(leaves)
    failure = RuntimeError("large acquisition cancelled")
    combined.set_exception(failure)
    assert child.done
    assert all(leaf.done for leaf in leaves[1:])
    assert not sequence.done
    assert not combined.done
    cleanup.set_finished()
    with pytest.raises(RuntimeError, match="large acquisition cancelled") as caught:
        combined.wait(timeout=1)
    assert caught.value is failure
    assert all(leaf.done for leaf in leaves)


@pytest.mark.parametrize("failed_watch", range(3))
def test_balanced_status_collection_keeps_all_failure_watchers(failed_watch):
    """
    Balancing cannot detach failure-only pairs while required work remains pending.
    """
    required = StatusBase()
    signals = [Signal(name=f"failure_{index}", value=0) for index in range(3)]
    watchers = [
        ExceptionStatus(signal, 1, run=False, exception=RuntimeError("watch failed"))
        for signal in signals
    ]
    combined = all_statuses([required, *watchers])
    assert all(signal._callbacks[signal.SUB_VALUE] for signal in signals)
    signals[failed_watch].put(1)
    with pytest.raises(RuntimeError):
        combined.wait(timeout=1)
    assert required.done
    assert all(not signal._callbacks[signal.SUB_VALUE] for signal in signals)


def test_top_level_composite_timeout_releases_owned_children():
    """
    Constructor timeout releases watchers even without a sequence or composite parent.
    """
    signal = Signal(name="standalone_timeout", value=0)
    watcher = SubscriptionStatus(signal, lambda **_: False, run=False)
    other = StatusBase()
    combined = AndStatus(watcher, other, timeout=0.01)
    with pytest.raises(TimeoutError):
        combined.wait(timeout=1)
    combined._callback_thread.join(timeout=1)
    assert not combined._callback_thread.is_alive()
    assert watcher.done
    assert other.done
    assert not signal._callbacks[signal.SUB_VALUE]
