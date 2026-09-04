"""A/B check: does the `timeout` constructor argument survive for a PSI positioner?

Run from the repository root with the ophyd_devices environment active:

    python audit/timeout_kwarg_demo.py

Background: `PSISimplePositionerBase(PSIDeviceBase, PositionerBase)` inherits from ophyd's
PositionerBase, whose __init__ also assigns `self._timeout` (its own move timeout). Earlier
revisions of the branch lost the constructor value on that path (`_timeout = None`); the
current revision keeps it. The [control] class shows the plain-ophyd baseline: there,
`timeout=30` reaches PositionerBase through **kwargs.

Expected output on the current branch (constructor path fixed):

    [control] Device+PositionerBase (no PSIDeviceBase), timeout=30:
        _timeout = 30
    [PSI]     PSISimplePositionerBase subclass,        timeout=30:
        _timeout = 30.0                 <-- kept (normalized to float)
        move(5).timeout = 30.0          <-- PositionerBase.move() default
        DeviceStatus(p).timeout = 30.0  <-- status default resolution

Output on an earlier revision of the branch (30006f74): all three PSI lines showed None.

Output on main (copy the script there): _timeout = 30, move(5).timeout = 30.0, and
DeviceStatus(p).timeout = None - the status default resolution does not exist there yet.

Note that this covers the *constructor* only. Through a BEC device config the value takes a
different route for positioners (ophyd's `timeout` property setter, no validation) - see
audit/README.md, step 7.
"""

import inspect

from ophyd import Component as Cpt
from ophyd import Device, Signal
from ophyd.positioner import PositionerBase

from ophyd_devices.interfaces.base_classes.psi_positioner_base import PSISimplePositionerBase
from ophyd_devices.utils.psi_device_base_utils import DeviceStatus

try:  # keep the output to the lines that matter
    from bec_lib.logger import bec_logger

    bec_logger.logger.remove()
except Exception:  # pragma: no cover
    pass


class SoftSetpoint(Signal):
    """Plain Signal that tolerates the `wait=` keyword an EpicsSignal would accept."""

    def put(self, value, *, wait=True, **kwargs):  # pylint: disable=unused-argument
        return super().put(value)


print("ophyd PositionerBase.__init__ signature:")
print(f"    {inspect.signature(PositionerBase.__init__)}")
print()


class ControlPositioner(Device, PositionerBase):
    """Same MRO shape, but WITHOUT PSIDeviceBase in between."""

    user_readback = Cpt(Signal, value=0.0)
    user_setpoint = Cpt(SoftSetpoint, value=0.0)


class DemoPositioner(PSISimplePositionerBase):
    """Minimal concrete PSISimplePositionerBase with soft signals."""

    user_readback = Cpt(Signal, value=0.0)
    user_setpoint = Cpt(SoftSetpoint, value=0.0)
    motor_done_move = Cpt(Signal, value=1)


ctrl = ControlPositioner(name="ctrl", timeout=30)
print("[control] Device+PositionerBase (no PSIDeviceBase), timeout=30:")
print(f"    _timeout = {ctrl._timeout}")

psi = DemoPositioner(name="demo", timeout=30)
print("[PSI]     PSISimplePositionerBase subclass,        timeout=30:")
print(f"    _timeout = {psi._timeout}")

# PositionerBase.move() falls back to self._timeout for the MoveStatus deadline:
move_status = psi.move(5.0, wait=False)
print(f"    move(5).timeout = {move_status.timeout}")
psi.stop()  # cancel the pending move status before exiting

# And the default-status-timeout feature resolves the same attribute:
print(f"    DeviceStatus(p).timeout = {DeviceStatus(psi).timeout}")
