from abc import ABC
from typing import TypedDict

from ophyd import Component as Cpt
from ophyd import Device
from ophyd.device import required_for_connection
from ophyd.positioner import PositionerBase
from ophyd.signal import EpicsSignalBase, Signal
from ophyd.status import MoveStatus
from ophyd.status import wait as status_wait
from ophyd.utils.epics_pvs import AlarmSeverity, fmt_time


class _SignalSentinel(object): ...


_OPTIONAL_SIGNAL = _SignalSentinel()
_REQUIRED_SIGNAL = _SignalSentinel()
_SIGNAL_NOT_AVAILABLE = "Signal not available"


class PSIPositionerException(Exception): ...


class RequiredSignalNotSpecified(PSIPositionerException): ...


class OptionalSignalNotSpecified(PSIPositionerException): ...


class SimplePositionerSignals(TypedDict, total=False):
    """The list of all the signals in the PSISimplePositionerBase"""

    user_readback: str
    user_setpoint: str
    motor_done_move: str
    velocity: str
    motor_stop: str


_SIMPLE_SIGNAL_NAMES = SimplePositionerSignals.__optional_keys__


class PositionerSignals(SimplePositionerSignals, total=False):
    """The list of all the signals in the PSIPositionerBase. See that class for
    documentation of signal functionality."""

    user_offset: str
    user_offset_dir: str
    offset_freeze_switch: str
    set_use_switch: str
    acceleration: str
    motor_egu: str
    motor_is_moving: str
    high_limit_switch: str
    low_limit_switch: str
    high_limit_travel: str
    low_limit_travel: str
    direction_of_travel: str
    home_forward: str
    home_reverse: str
    tolerated_alarm: str


_SIGNAL_NAMES = PositionerSignals.__optional_keys__


class PSISimplePositionerBase(ABC, Device, PositionerBase):
    """Base class for simple positioners."""

    SIGNAL_NAMES = _SIMPLE_SIGNAL_NAMES

    user_readback: EpicsSignalBase = _REQUIRED_SIGNAL
    user_setpoint: EpicsSignalBase = _OPTIONAL_SIGNAL
    velocity: EpicsSignalBase = _OPTIONAL_SIGNAL
    motor_stop: EpicsSignalBase = _OPTIONAL_SIGNAL
    motor_done_move: EpicsSignalBase = _OPTIONAL_SIGNAL

    stop_value = 1  # The value to put to the stop PV (if set) to make the motor stop
    done_value = 1  # The value expected to be reported by motor_done_move when the move is done
    use_put_complete = False  # Whether to use put-completion for the setpoint for the move status

    def __init__(
        self,
        prefix="",
        *,
        name,
        limits: list[float] | tuple[float, ...] | None = None,
        deadband: float | None = None,
        use_put_completion: bool | None = None,
        read_attrs=None,
        configuration_attrs=None,
        parent=None,
        override_suffixes: SimplePositionerSignals = {},
        **kwargs,
    ):
        """A simple positioner class, to provide the functionality of PVPositioner but behave more
        similarly to EpicsMotor.

        Args:
            name (str): (required) the name of the device
            limits (list | tuple | None): If given, a length-2 sequence within the range of which movement is allowed.
            deadband (float | None): If given, set a soft deadband of this absolute value, within which positioner moves will return immediately. If the positioner has no motor_done_move signal, you must provide this.
            use_put_completion (bool | None): If given, use put completion on the setpoint signal to resolve the move status.
            override_suffixes (dict[str, str]): a dictionary of signal_name: pv_suffix which will replace the values in the signal classvar.
        """
        super().__init__(
            prefix=prefix,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            name=name,
            parent=parent,
            **kwargs,
        )

        if limits is not None:
            self._limits = tuple(limits)
        else:
            self._limits = None
        self._deadband = deadband
        if use_put_completion is not None:
            self.use_put_complete = use_put_completion
        self._egu = kwargs.get("egu") or ""

        if (missing := self._remaining_defaults(_REQUIRED_SIGNAL)) != set():
            raise RequiredSignalNotSpecified(f"Signal(s) {missing} must be defined in a subclass")

        if self.user_readback is _OPTIONAL_SIGNAL and self.motor_done_move is _OPTIONAL_SIGNAL:
            raise ValueError(
                "Positioner must have at least one of user_readback and motor_done_move"
            )

        not_implemented = self._remaining_defaults(_OPTIONAL_SIGNAL)
        for signal_name, pv_suffix in override_suffixes.items():
            if signal_name not in not_implemented:
                component: Cpt[EpicsSignalBase] = getattr(self.__class__, signal_name)
                signal: EpicsSignalBase = getattr(self, signal_name)
                signal.__init__(
                    prefix + pv_suffix,
                    name=self.name + self._child_name_separator + signal_name,
                    **component.kwargs,
                )
            else:
                self.log.warning(
                    f"{self.__class__} does not implement overridden signal {signal_name}"
                )

        if self.user_readback is not _OPTIONAL_SIGNAL:
            self.user_readback.subscribe(self._pos_changed)
        if self.motor_done_move is not _OPTIONAL_SIGNAL:
            self.motor_done_move.subscribe(self._move_changed)
        elif deadband is None:
            raise ValueError("Deadband must not be None for a device with no done signal")

        # Make the default alias for the user_readback the name of the motor itself
        # for compatibility with EpicsMotor
        self.user_readback.name = self.name

    def _remaining_defaults(self, attr: _SignalSentinel) -> set[str]:
        return set(filter(lambda s: getattr(self, s) is attr, self.SIGNAL_NAMES))

    @property
    def egu(self):
        """The engineering units (EGU) for a position"""
        return self._egu

    def check_value(self, pos):
        """Check that the position is within the soft limits"""
        if self.limits is not None:
            low, high = self.limits
            if low != high and not (low <= pos <= high):
                raise ValueError(f"{pos} outside of user-specified limits {self.limits}")
        else:
            self.user_setpoint.check_value(pos)

    @property
    def moving(self):
        """Whether or not the motor is moving

        If a `done` PV is specified, it will be read directly to get the motion
        status. If not, it determined from the internal state of PVPositioner.

        Returns
        -------
        bool
        """
        dval = self.motor_done_move.get(use_monitor=False)
        return dval != self.done_value

    def _setup_move(self, position):
        """Move and do not wait until motion is complete (asynchronous)"""
        self.log.debug(f"{self.name}.user_setpoint = {position}")
        if not self.use_put_complete:
            self.user_setpoint.put(position, wait=True)
        else:
            self.user_setpoint.put(
                position, wait=False, callback=lambda *_: self._done_moving(success=True)
            )

    def move(self, position, wait=True, timeout=None, moved_cb=None):
        """Move to a specified position, optionally waiting for motion to
        complete.

        Parameters
        ----------
        position
            Position to move to
        moved_cb : callable
            Call this callback when movement has finished. This callback must
            accept one keyword argument: 'obj' which will be set to this
            positioner instance.
        timeout : float, optional
            Maximum time to wait for the motion. If None, the default timeout
            for this positioner is used.

        Returns
        -------
        status : MoveStatus

        Raises
        ------
        TimeoutError
            When motion takes longer than `timeout`
        ValueError
            On invalid positions
        RuntimeError
            If motion fails other than timing out
        """

        if self._deadband is not None and abs(position - self._position) < self._deadband:
            return MoveStatus(self, position, done=True, success=True)

        status = super().move(position, timeout=timeout, moved_cb=moved_cb)

        try:
            self._setup_move(position)
            if wait:
                status_wait(status)
        except KeyboardInterrupt:
            self.stop()
            raise

        return status

    @required_for_connection
    def _move_changed(self, timestamp=None, value=None, sub_type=None, **kwargs):
        was_moving = self._moving
        self._moving = value != self.done_value

        started = False
        if not self._started_moving:
            started = self._started_moving = not was_moving and self._moving
            self.log.debug(f"[ts={fmt_time(timestamp)}] {self.name} started moving: {started}")

        self.log.debug(
            f"[ts={fmt_time(timestamp)}] {self.name} moving: {self._moving} (value={value})"
        )
        if started:
            self._run_subs(sub_type=self.SUB_START, timestamp=timestamp, value=value, **kwargs)

        if self.motor_done_move is _OPTIONAL_SIGNAL:
            # if there is no motor_done_move, we came here from self._pos_changed with a value
            # based on whether whe are within the deadband
            if not self._moving:
                # we got a position update within the deadband of the setpoint, close out move statuses.
                self._run_subs(
                    sub_type=self._SUB_REQ_DONE, timestamp=timestamp, value=value, **kwargs
                )

    @required_for_connection
    def _pos_changed(self, timestamp=None, value=None, **kwargs):
        """Callback from EPICS, indicating a change in position"""
        self._set_position(value)
        if self.motor_done_move is _OPTIONAL_SIGNAL:
            # No DMOV, so we compare to the setpoint to see if we are done
            self._move_changed(
                timestamp=timestamp,
                value=(abs(self.user_setpoint.get() - value) < self._deadband),
                **kwargs,
            )

    def stop(self, *, success=False):
        if self.motor_stop is not _OPTIONAL_SIGNAL:
            self.motor_stop.put(self.stop_value, wait=False)
        super().stop(success=success)

    @property
    def report(self):
        rep = super().report
        rep["pv"] = self.user_readback.pvname
        return rep

    @property
    def limits(self):
        if self._limits is not None:
            return tuple(self._limits)
        else:
            return self.user_setpoint.limits

    @property
    def egu(self):
        return self._egu

    def _repr_info(self):
        yield from super()._repr_info()

        yield ("limits", self._limits)
        yield ("egu", self._egu)

    def _done_moving(self, **kwargs):
        self._move_changed(value=self.done_value)
        super()._done_moving(**kwargs)


class PSIPositionerBase(PSISimplePositionerBase):
    """Base class for positioners which are similar to a motor but do not implement
    all the required signals for an EpicsMotor or have different PV suffices."""

    SIGNAL_NAMES = _SIGNAL_NAMES

    # calibration dial <-> user
    # https://epics.anl.gov/bcda/synApps/motor/motorRecord.html#Fields_calib
    user_offset = _OPTIONAL_SIGNAL
    user_offset_dir = _OPTIONAL_SIGNAL
    # Fix the difference between the user and dial positions
    offset_freeze_switch = _OPTIONAL_SIGNAL
    set_use_switch = _OPTIONAL_SIGNAL

    # configuration
    acceleration = _OPTIONAL_SIGNAL
    motor_egu = _OPTIONAL_SIGNAL

    # motor status
    motor_is_moving = _OPTIONAL_SIGNAL
    high_limit_switch = _OPTIONAL_SIGNAL
    low_limit_switch = _OPTIONAL_SIGNAL
    high_limit_travel: Signal | _SignalSentinel = _OPTIONAL_SIGNAL
    low_limit_travel: Signal | _SignalSentinel = _OPTIONAL_SIGNAL
    direction_of_travel = _OPTIONAL_SIGNAL

    # commands
    home_forward = _OPTIONAL_SIGNAL
    home_reverse = _OPTIONAL_SIGNAL

    # alarm information
    tolerated_alarm = AlarmSeverity.NO_ALARM

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
            **kwargs,
        )
        if self.limits is not None:
            for sig, lim in (
                (self.low_limit_travel, self.limits[0]),
                (self.high_limit_travel, self.limits[1]),
            ):
                # If the limit signals are defined as soft signals, propagate the limits there
                if sig is not _OPTIONAL_SIGNAL and type(sig) is Signal:
                    sig.put(lim)

    @property
    def egu(self):
        if self.motor_egu is not _OPTIONAL_SIGNAL:
            return self.motor_egu.get()
        return self._egu
