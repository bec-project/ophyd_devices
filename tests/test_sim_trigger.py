"""BEC lifecycle and callback regressions for the simulated trigger gate."""

import subprocess
import sys
import textwrap
import threading

import pytest

from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.interfaces.protocols.bec_protocols import BECDeviceProtocol
from ophyd_devices.sim.sim_trigger import SimTriggerWithGate
from ophyd_devices.utils.psi_device_base_utils import StatusBase


def hold(gate, *, stage=False):
    """Arm and return the pending third trigger; optionally stage as BEC does."""
    gate.arm()
    if stage:
        gate.stage()
    for count in (1, 2):
        gate.trigger().wait(timeout=1)
        assert gate.value.get() == count
        assert not gate.waiting.get()
    status = gate.trigger()
    assert not status.done
    assert gate.value.get() == 3
    assert gate.waiting.get()
    return status


def assert_outcome(status, success):
    """Check the status outcome with a bounded wait."""
    if success:
        status.wait(timeout=1)
    else:
        with pytest.raises((RuntimeError, DeviceStoppedError)):
            status.wait(timeout=1)
    assert status.done
    assert status.success is success


@pytest.fixture
def gate():
    """Direct destruction must also clean up any pending acquisition."""
    device = SimTriggerWithGate("", name="gate")
    yield device
    device.destroy()


@pytest.fixture
def held_gate(gate):
    """Return a staged gate and its held status."""
    return gate, hold(gate, stage=True)


@pytest.fixture
def subscribe(gate):
    """Remove callbacks even when a test destroys their signals first."""
    registrations = []

    def register(signal, callback):
        signal.subscribe(callback, run=False)
        registrations.append((signal, callback))

    yield register
    for signal, callback in registrations:
        signal.clear_sub(callback)


@pytest.fixture
def worker(gate):
    """Capture thread errors and require every worker to finish."""
    threads, errors = [], []

    def start(function):
        def run():
            try:
                function()
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=run, daemon=True)
        threads.append(thread)
        thread.start()
        return thread

    yield start
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive(), "Gate operation did not finish"
    assert not errors, errors


def test_unarmed_triggers_and_device_contract(gate):
    """The BEC device returns repository statuses and remains unblocked until armed."""
    assert isinstance(gate, BECDeviceProtocol)
    assert isinstance(gate, PSIDeviceBase)
    for count in range(1, 5):
        status = gate.trigger()
        assert isinstance(status, StatusBase)
        assert_outcome(status, True)
        assert gate.value.get() == count
        assert not gate.waiting.get()


@pytest.mark.parametrize(
    "operation,success",
    [
        ("release", True),
        ("stop", False),
        ("successful_stop", True),
        ("unstage", False),
        ("destroy", False),
    ],
)
def test_lifecycle_resolves_pending_trigger(held_gate, operation, success):
    """Release and successful stop succeed; interruption fails pending work."""
    gate, status = held_gate
    if operation == "successful_stop":
        gate.stop(success=True)
    else:
        getattr(gate, operation)()
    assert_outcome(status, success)
    if operation == "destroy":
        assert gate.destroyed
    else:
        assert not gate.waiting.get()
        assert_outcome(gate.trigger(), True)
        assert gate.value.get() == 4


def test_pending_trigger_cannot_be_replaced(held_gate):
    """An overlapping command cannot lose the status or change its readback."""
    gate, status = held_gate
    for operation in (gate.arm, gate.trigger):
        with pytest.raises(RuntimeError, match="already held"):
            operation()
    assert gate.value.get() == 3
    assert gate.waiting.get()
    gate.release()
    assert_outcome(status, True)


@pytest.mark.parametrize("operation", ["release", "stop"])
def test_repeated_cleanup_and_rearm(held_gate, operation):
    """Cleanup is idempotent and rearming resets the trigger count for another scan."""
    gate, status = held_gate
    getattr(gate, operation)()
    getattr(gate, operation)()
    assert_outcome(status, operation == "release")
    assert not gate.waiting.get()
    next_status = hold(gate)
    gate.release()
    assert_outcome(next_status, True)


@pytest.mark.parametrize("operation", ["release", "stop"])
def test_complete_preserves_each_bec_request(held_gate, operation):
    """Every complete request owns a distinct pending status and instruction metadata."""
    gate, trigger = held_gate
    statuses = [trigger, gate.complete(), gate.complete()]
    completed = []
    for request_id, status in enumerate(statuses):
        assert all(status is not previous for previous in statuses[:request_id])
        assert not status.done
        status.__dict__["instruction"] = {"request_id": request_id}
        status.add_callback(lambda result: completed.append(result.instruction["request_id"]))
    assert trigger.instruction == {"request_id": 0}
    getattr(gate, operation)()
    for status in statuses:
        assert_outcome(status, operation == "release")
    assert sorted(completed) == [0, 1, 2]
    assert_outcome(gate.complete(), True)


def test_delayed_completion_does_not_stop_a_new_acquisition(held_gate, monkeypatch, worker):
    """Registering an old failure after rearming cannot stop the new trigger."""
    gate, old_trigger = held_gate
    entered, proceed = threading.Event(), threading.Event()
    original = old_trigger.add_callback
    completions = []

    def delayed_registration(callback):
        entered.set()
        assert proceed.wait(timeout=3), "Completion registration was not released"
        original(callback)

    monkeypatch.setattr(old_trigger, "add_callback", delayed_registration)
    thread = worker(lambda: completions.append(gate.complete()))
    try:
        assert entered.wait(timeout=1)
        gate.stop()
        assert_outcome(old_trigger, False)
        new_trigger = hold(gate)
    finally:
        proceed.set()
        thread.join(timeout=1)
    assert len(completions) == 1
    assert_outcome(completions[0], False)
    assert not new_trigger.done
    assert gate.waiting.get()
    gate.release()
    assert_outcome(new_trigger, True)


def test_release_reconciles_delayed_waiting_publication(gate, monkeypatch, worker):
    """A waiting write delayed across release cannot leave a stale true readback."""
    gate.arm()
    for _ in range(2):
        gate.trigger().wait(timeout=1)
    entered, proceed = threading.Event(), threading.Event()
    original = gate.waiting.put
    statuses = []

    def delayed_put(value, *args, **kwargs):
        if value:
            entered.set()
            assert proceed.wait(timeout=3), "Waiting publication was not released"
        original(value, *args, **kwargs)

    monkeypatch.setattr(gate.waiting, "put", delayed_put)
    thread = worker(lambda: statuses.append(gate.trigger()))
    try:
        assert entered.wait(timeout=1)
        gate.release()
    finally:
        proceed.set()
        thread.join(timeout=1)
    assert len(statuses) == 1
    assert_outcome(statuses[0], True)
    assert not gate.waiting.get()


def test_release_and_stop_preserve_resolution_ownership(held_gate, monkeypatch, worker):
    """Stop cannot change the outcome already claimed by a concurrent release."""
    gate, trigger = held_gate
    entered, proceed = threading.Event(), threading.Event()
    original = trigger.set_finished

    def delayed_finish():
        entered.set()
        assert proceed.wait(timeout=3), "Trigger completion was not released"
        original()

    monkeypatch.setattr(trigger, "set_finished", delayed_finish)
    release_thread = worker(gate.release)
    try:
        assert entered.wait(timeout=1)
        completion = gate.complete()
        assert completion is not trigger and not completion.done
        stop_thread = worker(gate.stop)
        stop_thread.join(timeout=1)
    finally:
        proceed.set()
        release_thread.join(timeout=1)
    assert_outcome(trigger, True)
    assert_outcome(completion, True)
    assert not gate.waiting.get()


def test_native_composite_and_late_stop_callback_do_not_deadlock():
    """Use a bounded subprocess so a broken lock cycle cannot hang fixture teardown."""
    script = textwrap.dedent("""
        import threading
        from ophyd.status import AndStatus as NativeAndStatus
        from ophyd_devices.sim.sim_trigger import SimTriggerWithGate
        from ophyd_devices.utils.psi_device_base_utils import StatusBase

        gate = SimTriggerWithGate("", name="gate")
        gate.arm()
        for _ in range(2):
            gate.trigger().wait(timeout=1)
        held = gate.trigger()
        completing, late_stop, stopped = (threading.Event() for _ in range(3))
        errors = []

        def allow_late_callback(status):
            completing.set()
            if not late_stop.wait(timeout=3):
                errors.append("Late callback never entered")

        held.add_callback(allow_late_callback)
        finished = StatusBase(obj=gate)
        finished.set_finished()
        composite = NativeAndStatus(held, finished)

        def stop_from_callback(status):
            late_stop.set()
            gate.stop()
            stopped.set()

        def run(operation):
            try:
                operation()
            except Exception as exc:
                errors.append(exc)

        release = threading.Thread(target=run, args=(gate.release,), daemon=True)
        late = threading.Thread(
            target=run, args=(lambda: held.add_callback(stop_from_callback),), daemon=True
        )
        release.start()
        assert completing.wait(timeout=2), "Release did not reach its callbacks"
        assert held.done
        late.start()
        release.join(timeout=2)
        late.join(timeout=2)
        assert not release.is_alive(), "Release deadlocked in the native composite"
        assert not late.is_alive(), "Late stop callback deadlocked on the gate lock"
        assert not errors, errors
        assert stopped.is_set()
        held.wait(timeout=1)
        composite.wait(timeout=1)
        assert held.success and not gate.waiting.get()
        gate.destroy()
        """)
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_readback_callback_preserves_nested_third_trigger(gate, subscribe):
    """A trigger started from value 2 cannot be replaced by the outer trigger."""
    nested = []
    subscribe(
        gate.value, lambda value, **kwargs: nested.append(gate.trigger()) if value == 2 else None
    )
    gate.arm()
    assert_outcome(gate.trigger(), True)
    assert_outcome(gate.trigger(), True)
    assert len(nested) == 1 and not nested[0].done
    assert gate.value.get() == 3 and gate.waiting.get()
    gate.release()
    assert_outcome(nested[0], True)
    assert not gate.waiting.get()


def test_idle_callback_stop_observes_successful_release(held_gate, subscribe):
    """Publishing idle after release cannot let its subscriber cancel the released status."""
    gate, status = held_gate
    calls = []

    def stop_when_idle(value, old_value, **kwargs):
        if old_value and not value:
            calls.append(True)
            gate.stop()

    subscribe(gate.waiting, stop_when_idle)
    gate.release()
    assert_outcome(status, True)
    assert calls == [True] and not gate.waiting.get()


@pytest.mark.parametrize("operation", ["release", "stop", "destroy"])
def test_readback_callback_resolves_pending_trigger(gate, subscribe, operation):
    """Resolving from value 3 cannot publish stale waiting or touch destroyed signals."""
    subscribe(
        gate.value, lambda value, **kwargs: getattr(gate, operation)() if value == 3 else None
    )
    gate.arm()
    for _ in range(2):
        gate.trigger().wait(timeout=1)
    status = gate.trigger()
    assert_outcome(status, operation == "release")
    if operation == "destroy":
        assert gate.destroyed
    else:
        assert not gate.waiting.get()
        assert_outcome(gate.complete(), True)


def test_completion_callback_preserves_new_hold(held_gate):
    """An old completion cannot publish idle over a new callback-created acquisition."""
    gate, old_trigger = held_gate
    nested = []
    old_trigger.add_callback(lambda status: nested.append(hold(gate)))
    gate.release()
    assert_outcome(old_trigger, True)
    assert len(nested) == 1 and not nested[0].done
    assert gate.waiting.get()
    gate.release()
    assert_outcome(nested[0], True)
    assert not gate.waiting.get()


def test_destroy_rejects_work_before_base_teardown_finishes(held_gate, monkeypatch, worker):
    """The base shutdown gap cannot accept a trigger that destruction would leave pending."""
    gate, status = held_gate
    entered, proceed = threading.Event(), threading.Event()
    original = gate.task_handler.shutdown

    def delayed_shutdown():
        entered.set()
        assert proceed.wait(timeout=3), "Device shutdown was not released"
        original()

    monkeypatch.setattr(gate.task_handler, "shutdown", delayed_shutdown)
    thread = worker(gate.destroy)
    try:
        assert entered.wait(timeout=1)
        assert_outcome(status, False)
        for operation in (gate.arm, gate.trigger):
            with pytest.raises(RuntimeError, match="destroyed"):
                operation()
    finally:
        proceed.set()
        thread.join(timeout=1)
    assert gate.destroyed
    gate.destroy()
