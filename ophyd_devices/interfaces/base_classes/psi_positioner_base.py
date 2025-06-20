from abc import ABC

from ophyd.device import Device
from ophyd.positioner import PositionerBase
from ophyd.signal import EpicsSignalBase

_OPTIONAL_SIGNAL = object()
_REQUIRED_SIGNAL = object()
_SIGNAL_NOT_AVAILABLE = "Signal not available"


class PSIPositionerException(Exception): ...


class RequiredSignalNotSpecified(PSIPositionerException): ...


class OptionalSignalNotSpecified(PSIPositionerException): ...


_SIGNAL_NAMES = {
    "user_readback",
    "user_setpoint",
    "user_offset",
    "user_offset_dir",
    "offset_freeze_switch",
    "set_use_switch",
    "velocity",
    "acceleration",
    "motor_egu",
    "motor_is_moving",
    "motor_done_move",
    "high_limit_switch",
    "low_limit_switch",
    "high_limit_travel",
    "low_limit_travel",
    "direction_of_travel",
    "motor_stop",
    "home_forward",
    "home_reverse",
    "tolerated_alarm",
}


class PSIPositionerBase(ABC, Device, PositionerBase):
    """Base class for positioners which are similar to a motor but do not implement
    all the required signals for an EpicsMotor or have different PV suffices."""

    # position
    user_readback = _REQUIRED_SIGNAL
    user_setpoint = _REQUIRED_SIGNAL

    # calibration dial <-> user
    user_offset = _OPTIONAL_SIGNAL
    user_offset_dir = _OPTIONAL_SIGNAL
    offset_freeze_switch = _OPTIONAL_SIGNAL
    set_use_switch = _OPTIONAL_SIGNAL

    # configuration
    velocity = _OPTIONAL_SIGNAL
    acceleration = _OPTIONAL_SIGNAL
    motor_egu = _OPTIONAL_SIGNAL

    # motor status
    motor_is_moving = _OPTIONAL_SIGNAL
    motor_done_move = _OPTIONAL_SIGNAL
    high_limit_switch = _OPTIONAL_SIGNAL
    low_limit_switch = _OPTIONAL_SIGNAL
    high_limit_travel = _OPTIONAL_SIGNAL
    low_limit_travel = _OPTIONAL_SIGNAL
    direction_of_travel = _OPTIONAL_SIGNAL

    # commands
    motor_stop = _OPTIONAL_SIGNAL
    home_forward = _OPTIONAL_SIGNAL
    home_reverse = _OPTIONAL_SIGNAL

    # alarm information
    tolerated_alarm = _OPTIONAL_SIGNAL

    def __init__(
        self,
        prefix="",
        *,
        name,
        kind=None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        child_name_separator="_",
        connection_timeout=...,
        **kwargs,
    ):
        super().__init__(
            prefix,
            name=name,
            kind=kind,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            parent=parent,
            child_name_separator=child_name_separator,
            connection_timeout=connection_timeout,
            **kwargs,
        )

        not_implemented = {
            signal for signal in _SIGNAL_NAMES if getattr(self, signal) is _REQUIRED_SIGNAL
        }
        if not_implemented != set():
            raise RequiredSignalNotSpecified(
                f"Signal(s) {not_implemented} must be defined in a subclass"
            )
        # Make the default alias for the user_readback the name of the motor itself
        # for compatibility with EpicsMotor
        self.user_readback.name = self.name
