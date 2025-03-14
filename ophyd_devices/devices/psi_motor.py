"""Extension class for EpicsMotor

This module extends the basic EpicsMotor with additional functionality. It
exposes additional parameters of the EPICS MotorRecord and provides a more
detailed interface for motors using the new ECMC-based motion systems at PSI.
"""

from ophyd import Component, EpicsMotor, EpicsSignal, EpicsSignalRO, Kind
from ophyd.status import DeviceStatus, MoveStatus
from ophyd.utils.errors import UnknownStatusFailure
from ophyd.utils.epics_pvs import AlarmSeverity


class SpmgStates:
    """Enum for the EPICS MotorRecord's SPMG state"""

    # pylint: disable=too-few-public-methods
    STOP = 0
    PAUSE = 1
    MOVE = 2
    GO = 3


class EpicsMotorMR(EpicsMotor):
    """Extended EPICS Motor class

    Special motor class that exposes additional motor record functionality.
    It extends EpicsMotor base class to provide some simple status checks
    before movement. Usage is the same as EpicsMotor.
    """

    tolerated_alarm = AlarmSeverity.INVALID

    motor_deadband = Component(EpicsSignalRO, ".RDBD", auto_monitor=True, kind=Kind.config)
    motor_mode = Component(
        EpicsSignal, ".SPMG", auto_monitor=True, put_complete=True, kind=Kind.omitted
    )
    motor_status = Component(EpicsSignal, ".STAT", auto_monitor=True, kind=Kind.omitted)
    motor_enable = Component(EpicsSignal, ".CNEN", auto_monitor=True, kind=Kind.omitted)

    def move(self, position, wait=True, **kwargs) -> MoveStatus:
        """Extended move function with a few sanity checks

        Note that the default EpicsMotor only supports the 'GO' movement mode.
        This could get it deadlock if it was previously explicitly stopped.
        """
        # Reset SPMG before move
        if self.motor_mode.get() != SpmgStates.GO:
            self.motor_mode.set(SpmgStates.GO).wait()
        # Warn if EPIC motorRecord claims an error (it's not easy to reset)
        status = self.motor_status.get()
        if status:
            self.log.warning(
                f"EPICS MotorRecord is in alarm state {status}, ophyd will raise"
            )
        # Warn if trying to move beyond an active limit
        # NOTE: VME limit switches active only in the direction of travel (or disconnected)
        # NOTE: SoftMotor limits are not propagated at all
        if self.high_limit_switch.get(use_monitor=False) and position > self.position:
            self.log.warning("Attempting to move above active HLS")
        if self.low_limit_switch.get(use_monitor=False) and position < self.position:
            self.log.warning("Attempting to move below active LLS")

        # EpicsMotor might raise if MR is in alarm
        try:
            status = super().move(position, wait, **kwargs)
            return status
        except UnknownStatusFailure:
            status = DeviceStatus(self)
            status.set_finished()
            # return status
            raise


class EpicsMotorEC(EpicsMotorMR):
    """Detailed ECMC EPICS motor class

    Special motor class to provide additional functionality  for ECMC based motors.
    It exposes additional diagnostic fields and includes basic error management.
    Usage is the same as EpicsMotor.
    """

    USER_ACCESS = ["reset"]
    motor_enable_readback = Component(EpicsSignalRO, "-EnaAct", auto_monitor=True, kind=Kind.normal)
    motor_enable = Component(
        EpicsSignalRO,
        "-EnaCmd-RB",
        write_pv="-EnaCmd",
        put_complete=True,
        auto_monitor=True,
        kind=Kind.normal,
    )
    homed = Component(EpicsSignalRO, "-Homed", auto_monitor=True, kind=Kind.normal)
    velocity_readback = Component(EpicsSignalRO, "-VelAct", auto_monitor=True, kind=Kind.normal)
    position_readback = Component(EpicsSignalRO, "-PosAct", auto_monitor=True, kind=Kind.normal)
    position_error = Component(EpicsSignalRO, "-PosErr", auto_monitor=True, kind=Kind.normal)
    # Virtual motor and temperature limits are interlocks
    high_interlock = Component(EpicsSignalRO, "-SumIlockFwd", auto_monitor=True, kind=Kind.normal)
    low_interlock = Component(EpicsSignalRO, "-SumIlockBwd", auto_monitor=True, kind=Kind.normal)

    # ecmc_status = Component(EpicsSignalRO, "-Status", auto_monitor=True, kind=Kind.normal)
    error = Component(EpicsSignalRO, "-ErrId", auto_monitor=True, kind=Kind.normal)
    error_msg = Component(EpicsSignalRO, "-MsgTxt", auto_monitor=True, kind=Kind.normal)
    error_reset = Component(EpicsSignal, "-ErrRst", put_complete=True, kind=Kind.omitted)

    def move(self, position, wait=True, **kwargs) -> MoveStatus:
        """Extended move function with a few sanity checks

        Note that the default EpicsMotor only supports the 'GO' movement mode.
        This could get it deadlock if it was previously explicitly stopped.
        In addition to parent method, this also checks the ECMC error status
        before moving.
        """
        # Check ECMC error status before move
        error = self.error.get()
        if error:
            raise RuntimeError(f"Motor is in error state with message: '{self.error_msg.get()}'")

        # Warn if trying to move beyond an active limit
        if self.high_interlock.get(use_monitor=False) and position > self.position:
            self.log.warning("Attempting to move above active HLS or Ilock")
        if self.high_interlock.get(use_monitor=False) and position < self.position:
            self.log.warning("Attempting to move below active LLS or Ilock")

        return super().move(position, wait, **kwargs)

    def reset(self):
        """Resets an ECMC axis

        Recovers an ECMC axis from a previous error. Note that this does not
        solve the cause of the error, that you'll have to do yourself.

        Common error causes:
        -------------------------
        - MAX_POSITION_LAG_EXCEEDED : The PID tuning is wrong, tolerance is too
                low,  acceleration is too high, scaling is off, or the motor
                lacks torque.
        - MAX_VELOCITY_EXCEEDED : PID is wrong or the motor is sticking-slipping
        - BOTH_LIMITS_ACTIVE : The motors are probably not connected
        - HW_ERROR : Tricky one, usually the drive power supply is cut due to
                fuse or safety, might need to push physical buttons.
        """
        # Reset the error
        self.error_reset.set(1, settle_time=0.2).wait()
        # Check if it disappeared
        if self.error.get():
            raise RuntimeError(f"Failed to reset axis, still in error: '{self.error_msg.get()}'")
