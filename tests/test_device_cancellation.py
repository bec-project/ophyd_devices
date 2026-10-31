"""Device cancellation permits new work after a previous stop."""

import pytest
from ophyd import Component, Signal

from ophyd_devices.interfaces.base_classes.psi_device_base import DeviceStoppedError, PSIDeviceBase
from ophyd_devices.utils.psi_device_base_utils import CompareStatus


class ResourceDevice(PSIDeviceBase):
    """Acquisition and cleanup acknowledgements use distinct live signals."""

    value = Component(Signal, value=0)
    ready = Component(Signal, value=0)


def finish_for_cleanup(status):
    """Retire test-owned pending work even when the regression assertion fails."""
    if status is not None and not status.done:
        status.set_exception(RuntimeError("Test cleanup"))


def test_registration_after_stop_can_complete_without_staging():
    owner = ResourceDevice(name="owner")
    pending = None
    try:
        owner.stop()
        pending = CompareStatus(owner.value, 1, run=False)
        owner.cancel_on_stop(pending)
        assert not pending.done
        owner.value.put(1)
        pending.wait(timeout=0.1)
        assert pending.success
        assert not owner.value._callbacks[owner.value.SUB_VALUE]
        assert not owner._stoppable_status_objects
    finally:
        finish_for_cleanup(pending)
        owner.destroy()


def test_later_stop_cancels_work_registered_after_previous_stop():
    owner = ResourceDevice(name="owner")
    try:
        owner.stop()
        pending = CompareStatus(owner.value, 1, run=False)
        owner.cancel_on_stop(pending)
        assert not pending.done
        owner.stop()
        with pytest.raises(DeviceStoppedError):
            pending.wait(timeout=0.1)
        assert not owner.value._callbacks[owner.value.SUB_VALUE]
    finally:
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
