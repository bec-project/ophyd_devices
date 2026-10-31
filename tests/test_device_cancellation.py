"""Registered acknowledgements are bounded and tolerate native completion races."""

import threading

import pytest
from ophyd import Component, Signal

from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.utils.psi_device_base_utils import CompareStatus, SequenceStatus, StatusBase


class ResourceDevice(PSIDeviceBase):
    value = Component(Signal, value=5)
    ready = Component(Signal, value=0)


def test_completed_and_duplicate_statuses_do_not_accumulate():
    owner = ResourceDevice(name="owner")
    try:
        for _ in range(100):
            status = StatusBase()
            owner.cancel_on_stop(status)
            owner.cancel_on_stop(status)
            assert owner._stoppable_status_objects == [status]
            status.set_finished()
            owner.cancel_on_stop(status)
            assert not owner._stoppable_status_objects
    finally:
        owner.destroy()


def test_stop_cancels_sequence_and_awaits_its_signal_cleanup():
    owner = ResourceDevice(name="owner")
    acknowledgement = CompareStatus(owner.ready, 1, run=False)

    def cleanup(error):
        owner.value.put(0)
        return acknowledgement

    sequence = SequenceStatus(steps=[lambda: StatusBase()], on_failure=cleanup)
    owner.cancel_on_stop(sequence)
    try:
        owner.stop()
        assert owner.value.get() == 0
        assert not sequence.done
        assert owner._stoppable_status_objects == [sequence]
        owner.ready.put(1)
        with pytest.raises(DeviceStoppedError):
            sequence.wait(timeout=1)
        assert not owner._stoppable_status_objects
    finally:
        owner.ready.put(1)
        owner.destroy()


def test_stop_tolerates_completion_committed_before_callbacks_finish(monkeypatch):
    owner = ResourceDevice(name="owner")
    entered, release = threading.Event(), threading.Event()
    status = StatusBase(timeout=60)
    settled = status._settled

    def finish():
        entered.set()
        assert release.wait(timeout=2)
        settled()

    monkeypatch.setattr(status, "_settled", finish)
    owner.cancel_on_stop(status)
    try:
        status.set_finished()
        assert entered.wait(timeout=1)
        owner.stop()
    finally:
        release.set()
        status._callback_thread.join(timeout=1)
        assert not status._callback_thread.is_alive()
        owner.destroy()
    assert status.success
