"""
Module for undulator control
"""

from ophyd import EpicsSignal, EpicsSignalRO, PVPositioner
from ophyd.device import Component as Cpt
from ophyd.status import MoveStatus


class UndulatorGap(PVPositioner):
    """
    SLS Undulator gap control
    """

    setpoint = Cpt(EpicsSignal, suffix="GAP-SP")
    readback = Cpt(EpicsSignal, suffix="GAP-RBV", kind="hinted", auto_monitor=True)

    stop_signal = Cpt(EpicsSignal, suffix="STOP")
    done = Cpt(EpicsSignalRO, suffix="DONE", auto_monitor=True)

    select_control = Cpt(EpicsSignalRO, suffix="SCTRL", auto_monitor=True)

    def __init__(
        self,
        prefix="",
        *,
        limits=None,
        name=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        egu="",
        **kwargs,
    ):
        super().__init__(
            prefix=prefix,
            limits=limits,
            name=name,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            egu=egu,
            **kwargs,
        )
        # Make the default alias for the user_readback the name of the
        # motor itself.
        self.readback.name = self.name

    def move(self, position, wait=True, timeout=None, moved_cb=None):

        # If it is operator controlled, undulator will not move.
        if self.select_control.get() == 0:
            raise Exception("Undulator is operator controlled!")

        # If it is already there, undulator will not move. The done flag
        # will not change, the moving change callback will not be called.
        # The status will not change.
        if abs(position - self._position) < 0.0008:
            status = MoveStatus(self, position, done=True, success=True)
            return status

        return super().move(position, wait=wait, timeout=timeout, moved_cb=moved_cb)
