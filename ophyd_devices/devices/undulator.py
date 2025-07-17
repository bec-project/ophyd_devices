"""
Module for undulator control
"""

from __future__ import annotations

import enum

from bec_lib.logger import bec_logger
from ophyd import EpicsSignal, EpicsSignalRO, PVPositioner
from ophyd.device import Component as Cpt
from ophyd.signal import DEFAULT_CONNECTION_TIMEOUT, DEFAULT_WRITE_TIMEOUT
from ophyd.status import MoveStatus

logger = bec_logger.logger


class UNDULATORCONTROL(int, enum.Enum):
    """
    Enum for undulator control modes.
    """

    OPERATOR = 0
    BEAMLINE = 1


class UndulatorEpicsSignal(EpicsSignal):
    """
    SLS Undulator setpoint control
    """

    def put(
        self,
        value,
        force=False,
        connection_timeout=DEFAULT_CONNECTION_TIMEOUT,
        callback=None,
        use_complete=None,
        timeout=DEFAULT_WRITE_TIMEOUT,
        **kwargs,
    ):
        """
        Put a value to the setpoint PV.

        If the undulator is operator controlled, it will not move.
        """
        if self.parent.select_control.get() == UNDULATORCONTROL.OPERATOR.value:
            raise PermissionError(
                f"Cannot use put for signal {self.name}; Undulator is operator controlled!"
            )
        return super().put(
            value,
            force=force,
            connection_timeout=connection_timeout,
            callback=callback,
            use_complete=use_complete,
            timeout=timeout,
            **kwargs,
        )


class UndulatorGap(PVPositioner):
    """
    SLS Undulator gap control
    """

    setpoint = Cpt(UndulatorEpicsSignal, suffix="GAP-SP")
    readback = Cpt(EpicsSignal, suffix="GAP-RBV", kind="hinted", auto_monitor=True)

    stop_signal = Cpt(UndulatorEpicsSignal, suffix="STOP")
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
        self.readback._metadata["write_access"] = False

    def move(self, position, wait=True, timeout=None, moved_cb=None):

        # If it is operator controlled, undulator will not move.
        if self.select_control.get() == 0:
            raise PermissionError("Undulator is operator controlled!")

        # If it is already there, undulator will not move. The done flag
        # will not change, the moving change callback will not be called.
        # The status will not change.
        if self._position is not None and abs(position - self._position) < 0.0008:
            logger.info(
                f"Undulator gap {self.name} already close to position {position}, not moving."
            )
            status = MoveStatus(self, position, done=True, success=True)
            return status

        return super().move(position, wait=wait, timeout=timeout, moved_cb=moved_cb)
