"""
Module for undulator control
"""

from ophyd import EpicsSignal, EpicsSignalRO
from ophyd.device import Component as Cpt

from ophyd_devices.interfaces.base_classes.psi_positioner_base import PSISimplePositionerBase


class UndulatorGap(PSISimplePositionerBase):
    """
    SLS Undulator gap control
    """

    user_setpoint = Cpt(EpicsSignal, suffix="GAP-SP")
    user_readback = Cpt(EpicsSignal, suffix="GAP-RBV", kind="hinted", auto_monitor=True)

    motor_stop = Cpt(EpicsSignal, suffix="STOP")
    motor_done_move = Cpt(EpicsSignalRO, suffix="DONE", auto_monitor=True)

    select_control = Cpt(EpicsSignalRO, suffix="SCTRL", auto_monitor=True)

    def move(self, position, wait=True, timeout=None, moved_cb=None):
        # If it is operator controlled, undulator will not move.
        if self.select_control.get() == 0:
            raise RuntimeError("Undulator is operator controlled!")
        return super().move(position, wait=wait, timeout=timeout, moved_cb=moved_cb)
