"""Extension class for EpicsMotor

This module extends the basic EpicsMotor with additional functionality. It
exposes additional parameters of the EPICS MotorRecord and provides a more
detailed interface for motors using the new ECMC-based motion systems at PSI.
"""

import functools

from ophyd import Component as Cpt
from ophyd import EpicsMotor as OphydEpicsMotor
from ophyd import EpicsSignal, EpicsSignalRO, Kind
from ophyd.status import MoveStatus
from ophyd.utils.epics_pvs import AlarmSeverity, fmt_time
from ophyd.utils.errors import UnknownStatusFailure


class SpmgStates:
    """Enum for the EPICS MotorRecord's SPMG state"""

    STOP = 0
    PAUSE = 1
    MOVE = 2
    GO = 3


class EpicsSignalWithCheck(EpicsSignal):
    """
    Custom EpicsSignal with a value check on put.
    """

    def put(self, value, use_complete: bool = True, **kwargs):
        """
        Override put method to handle travel limits.

        This method allows setting the travel limits for the ECMC motor.
        It ensures that the value is within the acceptable range before
        sending it to the EPICS server.
        """
        if not use_complete:
            use_complete = True
            self.log.warning(f"Overruling use_complete for {self.pvname} to True")
        # Put the value with use_complete=True
        super().put(value, use_complete=use_complete, **kwargs)
        # Check if the value was accepted
        new_value = self.get(auto_monitor=False)
        if new_value != value:
            raise ValueError(f"Failed to set signal {self.name} to value: {value}.")


class EpicsMotor(OphydEpicsMotor):
    """
    Extended EPICS Motor class for PSI motors.


    Special motor class that exposes additional motor record functionality.
    It extends EpicsMotor base class to provide some simple status checks
    before movement. Usage is the same as EpicsMotor.
    """

    tolerated_alarm = AlarmSeverity.MINOR

    motor_deadband = Cpt(
        EpicsSignal, ".RDBD", auto_monitor=True, kind=Kind.omitted, doc="Retry Deadband (EGU)"
    )
    motor_mode = Cpt(
        EpicsSignal,
        ".SPMG",
        auto_monitor=True,
        put_complete=True,
        kind=Kind.omitted,
        doc="SPMG mode. Either Stop(0), Pause(1), Move(2) or Go(3).",
    )
    motor_status = Cpt(
        EpicsSignal, ".STAT", auto_monitor=True, kind=Kind.omitted, doc="Alarm status"
    )
    motor_enable = Cpt(
        EpicsSignal,
        ".CNEN",
        auto_monitor=True,
        kind=Kind.omitted,
        doc="Enable control. Either 0 (disabled) or 1 (enabled).",
    )
    high_limit_travel = Cpt(EpicsSignalWithCheck, ".HLM", kind=Kind.omitted, auto_monitor=True)
    low_limit_travel = Cpt(EpicsSignalWithCheck, ".LLM", kind=Kind.omitted, auto_monitor=True)

    def _check_motion_status(self) -> tuple[bool, Exception | None]:
        """Check if the motion finished successfully"""
        success = True
        exc = None
        # Check if we are at limit switches
        if self.low_limit_switch.get(use_monitor=False) == 1:
            success = False
            exc = RuntimeError(f"Motor {self.name} hit the low limit switch during motion")
        if self.high_limit_switch.get(use_monitor=False) == 1:
            success = False
            exc = RuntimeError(f"Motor {self.name} hit the high limit switch during motion")

        # Check the severity of the alarm field after motion is complete.
        # If there is any alarm at all warn the user, and if the alarm is
        # greater than what is tolerated, mark the move as unsuccessful
        severity = self.user_readback.alarm_severity

        if severity != AlarmSeverity.NO_ALARM:
            status = self.user_readback.alarm_status
            if severity > self.tolerated_alarm:
                self.log.error(
                    "Motion failed: %s is in an alarm state " "status=%s severity=%s",
                    self.name,
                    status,
                    severity,
                )
                success = False
                exc = RuntimeError(
                    f"Motor {self.name} is in an alarm state "
                    f"status={status} severity={severity}"
                )
            else:
                self.log.warning(
                    "Motor %s raised an alarm during motion " "status=%s severity %s",
                    self.name,
                    status,
                    severity,
                )

        return success, exc

    def _move_changed(self, timestamp=None, value=None, sub_type=None, **kwargs):
        """Callback from EPICS, indicating that movement status has changed"""
        was_moving = self._moving
        self._moving = value != 1

        started = False
        if not self._started_moving:
            started = self._started_moving = not was_moving and self._moving

        self.log.debug(
            "[ts=%s] %s moving: %s (value=%s)", fmt_time(timestamp), self, self._moving, value
        )

        if started:
            self._run_subs(sub_type=self.SUB_START, timestamp=timestamp, value=value, **kwargs)

        if was_moving and not self._moving:
            success, exc = self._check_motion_status()
            self._done_moving(success=success, timestamp=timestamp, value=value, exception=exc)

    def _done_moving(self, success=True, timestamp=None, value=None, **kwargs):
        """Overload PositionerBase._done_moving to pass kwargs to _SUB_REQ_DONE callbacks."""
        if success:
            self._run_subs(sub_type=self.SUB_DONE, timestamp=timestamp, value=value)

        self._run_subs(sub_type=self._SUB_REQ_DONE, success=success, timestamp=timestamp, **kwargs)
        self._reset_sub(self._SUB_REQ_DONE)

    def move(self, position, wait=False, moved_cb=None, timeout=None, **kwargs) -> MoveStatus:
        """Extended move function with a few sanity checks

        Note that the default EpicsMotor only supports the 'GO' movement mode.
        This could get it deadlock if it was previously explicitly stopped.
        """
        # Reset SPMG before move
        if self.motor_mode.get() != SpmgStates.GO:
            self.motor_mode.set(SpmgStates.GO).wait(timeout=5)
        # Warn if EPIC motorRecord claims an error (it's not easy to reset)
        status = self.motor_status.get()
        if status:
            self.log.warning(f"EPICS MotorRecord is in alarm state {status}, ophyd will raise")
        # Warn if trying to move beyond an active limit
        # NOTE: VME limit switches active only in the direction of travel (or disconnected)
        # NOTE: SoftMotor limits are not propagated at all
        if self.high_limit_switch.get(use_monitor=False) and position > self.position:
            self.log.warning("Attempting to move above active HLS")
        if self.low_limit_switch.get(use_monitor=False) and position < self.position:
            self.log.warning("Attempting to move below active LLS")

        self._started_moving = False

        # Modified PositionerBase.move method to call set_finished/set_exception instead of
        # deprecated _finished on the status object.
        if timeout is None:
            timeout = self._timeout

        self.check_value(position)

        self._run_subs(sub_type=self._SUB_REQ_DONE, success=False)
        self._reset_sub(self._SUB_REQ_DONE)

        status = MoveStatus(self, position, timeout=timeout, settle_time=self._settle_time)

        if moved_cb is not None:
            status.add_callback(functools.partial(moved_cb, obj=self))
            # the status object will run this callback when finished

        def set_status(success, exception=None, **kwargs):
            if success:
                status.set_finished()
            else:
                if exception is None:
                    exception = UnknownStatusFailure(f"{self.name} failed to move to {position}")
                status.set_exception(exception)

        self.subscribe(set_status, event_type=self._SUB_REQ_DONE, run=False)

        self.user_setpoint.put(position, wait=False)
        try:
            if wait:
                status.wait(timeout)
        except KeyboardInterrupt:
            self.stop()
            raise
        return status


class EpicsMotorEC(EpicsMotor):
    """Detailed ECMC EPICS motor class

    Special motor class to provide additional functionality  for ECMC based motors.
    It exposes additional diagnostic fields and includes basic error management.
    Usage is the same as EpicsMotor.
    """

    USER_ACCESS = ["reset"]
    motor_enabled = Cpt(
        EpicsSignalRO,
        "-EnaAct",
        auto_monitor=True,
        kind=Kind.omitted,
        doc="[ECMC] Reflects whether the axis is enabled in the hardware level.",
    )
    motor_enable = Cpt(
        EpicsSignal,
        "-EnaCmd-RB",
        write_pv="-EnaCmd",
        put_complete=True,
        kind=Kind.omitted,
        doc="[ECMC] Send enable/disable command to hardware.",
    )
    homed = Cpt(EpicsSignalRO, "-Homed", kind=Kind.omitted, doc="[ECMC] Homed status")
    velocity_readback = Cpt(
        EpicsSignalRO, "-VelAct", kind=Kind.omitted, doc="[ECMC] Velocity readback"
    )
    position_readback_dial = Cpt(
        EpicsSignalRO, "-PosAct", kind=Kind.omitted, doc="[ECMC] Position readback"
    )
    position_error = Cpt(EpicsSignalRO, "-PosErr", kind=Kind.omitted, doc="[ECMC] Position error")
    # Virtual motor and temperature limits are interlocks
    high_interlock = Cpt(EpicsSignalRO, "-SumIlockFwd", kind=Kind.omitted)
    low_interlock = Cpt(EpicsSignalRO, "-SumIlockBwd", kind=Kind.omitted)

    error = Cpt(
        EpicsSignalRO, "-ErrId", auto_monitor=True, kind=Kind.omitted, doc="[ECMC] Error ID"
    )
    error_reset = Cpt(EpicsSignal, "-ErrRst", put_complete=True, kind=Kind.omitted)
    message_text = Cpt(
        EpicsSignalRO, "-MsgTxt", auto_monitor=True, kind=Kind.omitted, doc="[ECMC] Message text"
    )

    def _check_motion_status(self) -> tuple[bool, Exception | None]:
        success, exception = super()._check_motion_status()
        if success:
            # Additionally check for ECMC errors
            error = self.error.get(use_monitor=False)
            if error:
                success = False
                message_text = self.message_text.get(use_monitor=False)
                exception = RuntimeError(f"Motor {self.name} reported ECMC error '{message_text}'")
        return success, exception

    def move(self, position, wait=False, **kwargs) -> MoveStatus:
        """Extended move function with a few sanity checks

        Check ECMC error and interlocks. They may get cleared by the move command. If not, exception
        will be raised.
        """
        # Check ECMC error status before move
        error = self.error.get()
        if error:
            self.log.warning(f"Motor is in error state with message: '{self.message_text.get()}'")

        # Warn if trying to move beyond an active limit
        if self.high_interlock.get(use_monitor=False) and position > self.position:
            self.log.warning("Attempting to move above active HLS or Ilock")
        if self.low_interlock.get(use_monitor=False) and position < self.position:
            self.log.warning("Attempting to move below active LLS or Ilock")

        return super().move(position, wait, **kwargs)

    def reset_error(self):
        """Resets an ECMC axis error.

        Recovers an ECMC axis from a previous error. Note that this does not
        solve the cause of the error, that you'll have to do yourself.

        Common error causes:
        -------------------------
        - MAX_POSITION_LAG_EXCEEDED : The PID tuning is wrong, tolerance is too low, acceleration
                is too high, scaling is off, or the motor lacks torque.
        - MAX_VELOCITY_EXCEEDED : PID is wrong or the motor is sticking-slipping.
        - BOTH_LIMITS_ACTIVE : The motors are probably not connected.
        - HW_ERROR : Tricky one, usually the drive power supply is cut due to fuse or safety. You
                might need to push physical buttons.
        """
        # Reset the error
        self.error_reset.set(1, settle_time=0.2).wait(timeout=5)  # block for 5s
        # Check if it disappeared
        error = self.error.get(auto_monitor=False)
        if error:
            message_text = self.message_text.get(auto_monitor=False)
            raise RuntimeError(f"Failed to reset axis, still in error '{message_text}'")
