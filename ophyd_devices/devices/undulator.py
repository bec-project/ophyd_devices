"""
Module for undulator control
"""

from __future__ import annotations

import enum

from bec_lib.logger import bec_logger
from ophyd import EpicsSignal, EpicsSignalRO, PVPositioner
from ophyd.device import Component as Cpt
from ophyd.signal import DEFAULT_CONNECTION_TIMEOUT, DEFAULT_WRITE_TIMEOUT

from ophyd_devices.utils.psi_device_base_utils import MoveStatus

logger = bec_logger.logger


class UNDULATORCONTROL(int, enum.Enum):
    """
    Enum for undulator control modes.
    """

    OPERATOR = 0
    BEAMLINE = 1


class UndulatorSetpointSignal(EpicsSignal):
    """
    SLS Undulator setpoint control
    """

    parent: UndulatorBase

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
        self.parent.validate_control()
        return super().put(
            value,
            force=force,
            connection_timeout=connection_timeout,
            callback=callback,
            use_complete=use_complete,
            timeout=timeout,
            **kwargs,
        )


class UndulatorStopSignal(EpicsSignal):
    """
    SLS Undulator stop signal"""

    parent: UndulatorBase

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
        Put a value to the stop PV.

        If any control validation fails, leave the stop PV unchanged.
        """
        try:
            self.parent.validate_control()
        except PermissionError:
            return None
        return super().put(
            value,
            force=force,
            connection_timeout=connection_timeout,
            callback=callback,
            use_complete=use_complete,
            timeout=timeout,
            **kwargs,
        )


class UndulatorBase(PVPositioner):
    """Undulator positioner with extensible control validations.

    Each rule contains a parent signal name, its required value or list of allowed
    values, and the error message raised when the value does not match. Derived
    classes can add signals and extend the immutable rules without changing the
    inherited signal classes::

        class EnabledUndulator(UndulatorGap):
            enabled = Cpt(EpicsSignalRO, "ENABLED")
            control_validations = UndulatorGap.control_validations + (
                ("enabled", [1, 2], "Undulator is disabled!"),
            )

    The rules apply to moves, direct setpoint writes, and stop writes. Stop writes
    silently skip the command when a rule fails.
    """

    control_validations: tuple[tuple[str, object, str], ...] = (
        ("select_control", UNDULATORCONTROL.BEAMLINE.value, "Undulator is operator controlled!"),
    )

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
        if self.readback is not None:
            self.readback.name = self.name
            self.readback._metadata["write_access"] = False
        else:
            self.setpoint.name = self.name

    def move(self, position, wait=True, timeout=None, moved_cb=None):
        """Validate control and use DONE to determine movement completion."""
        self.validate_control()
        return super().move(position, wait=wait, timeout=timeout, moved_cb=moved_cb)

    def validate_control(self) -> None:
        """Require equality with scalar targets or membership in list targets."""
        for signal_name, target, error_message in self.control_validations:
            value = getattr(self, signal_name).get()
            matches = value in target if isinstance(target, list) else value == target
            if not matches:
                raise PermissionError(error_message)


class UndulatorAlpha(UndulatorBase):
    """
    SLS Undulator alpha control.
    Angle of the linear polarization in relation to the horizontal plane.
    """

    setpoint = Cpt(UndulatorSetpointSignal, suffix="ALPHA", kind="hinted", auto_monitor=True)

    stop_signal = Cpt(UndulatorStopSignal, suffix="STOP", kind="omitted", auto_monitor=True)
    done = Cpt(EpicsSignalRO, suffix="DONE", kind="omitted", auto_monitor=True)

    select_control = Cpt(EpicsSignalRO, suffix="SCTRL", auto_monitor=True)


class UndulatorHarmonic(UndulatorBase):
    """
    SLS Undulator harmonic control
    """

    setpoint = Cpt(UndulatorSetpointSignal, suffix="HARMONIC", kind="hinted", auto_monitor=True)

    stop_signal = Cpt(UndulatorStopSignal, suffix="STOP", kind="omitted", auto_monitor=True)
    done = Cpt(EpicsSignalRO, suffix="DONE", kind="omitted", auto_monitor=True)

    select_control = Cpt(EpicsSignalRO, suffix="SCTRL", auto_monitor=True)


class UndulatorGap(UndulatorBase):
    """
    SLS Undulator gap control
    """

    setpoint = Cpt(UndulatorSetpointSignal, suffix="GAP-SP", kind="normal", auto_monitor=True)
    readback = Cpt(EpicsSignalRO, suffix="GAP-RBV", kind="hinted", auto_monitor=True)

    stop_signal = Cpt(UndulatorStopSignal, suffix="STOP", auto_monitor=True)
    done = Cpt(EpicsSignalRO, suffix="DONE", auto_monitor=True)

    select_control = Cpt(EpicsSignalRO, suffix="SCTRL", auto_monitor=True)

    def move(self, position, wait=True, timeout=None, moved_cb=None):
        # If it is already there, undulator will not move. The done flag
        # will not change, the moving change callback will not be called.
        # The status will not change.
        if self._position is not None and abs(position - self._position) < 0.0008:
            self.validate_control()
            logger.info(
                f"Undulator gap {self.name} already close to position {position}, not moving."
            )
            status = MoveStatus(self, position, done=True, success=True)
            return status

        return super().move(position, wait=wait, timeout=timeout, moved_cb=moved_cb)
