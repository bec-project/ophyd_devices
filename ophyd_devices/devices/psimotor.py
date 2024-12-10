""" Extension class for EpicsMotor

This module extends the basic EpicsMotor with additional functionality. It
exposes additional parameters of the EPICS MotorRecord and provides a more
detailed interface for motors using the new ECMC-based motion systems at PSI.
"""

import warnings

from ophyd import Component, EpicsMotor, EpicsSignal, EpicsSignalRO, Kind
from ophyd.status import DeviceStatus, MoveStatus
from ophyd.utils.errors import UnknownStatusFailure
from ophyd.utils.epics_pvs import AlarmSeverity


class SpmgStates:
    """ Enum for the EPICS MotorRecord's SPMG state"""
    # pylint: disable=too-few-public-methods
    STOP = 0
    PAUSE = 1
    MOVE = 2
    GO = 3


class EpicsMotorMR(EpicsMotor):
    """ Extended EPICS Motor class

    Special motor class that exposes additional motor record functionality.
    It extends EpicsMotor base class to provide some simple status checks
    before movement.
    """
    tolerated_alarm = AlarmSeverity.INVALID

    motor_deadband = Component(
        EpicsSignalRO, ".RDBD", auto_monitor=True, kind=Kind.config)
    motor_mode = Component(
        EpicsSignal, ".SPMG", auto_monitor=True, put_complete=True, kind=Kind.omitted)
    motor_status = Component(
        EpicsSignal, ".STAT", auto_monitor=True, kind=Kind.omitted)
    motor_enable = Component(
        EpicsSignal, ".CNEN", auto_monitor=True, kind=Kind.omitted)

    def move(self, position, wait=True, **kwargs) -> MoveStatus:
        """ Extended move function with a few sanity checks

        Note that the default EpicsMotor only supports the 'GO' movement mode.
        """
        # Reset SPMG before move
        spmg = self.motor_mode.get()
        if spmg != SpmgStates.GO:
            self.motor_mode.set(SpmgStates.GO).wait()
        # Warn if EPIC motorRecord claims an error
        status = self.motor_status.get()
        if status:
            warnings.warn(
                f"EPICS MotorRecord is in alarm state {status}, ophyd will raise",
                RuntimeWarning
                )
        # Warni if trying to move beyond an active limit
        # if self.high_limit_switch and position > self.position:
        #     warnings.warn("Attempting to move above active HLS", RuntimeWarning)
        # if self.low_limit_switch and position < self.position:
        #     warnings.warn("Attempting to move below active LLS", RuntimeWarning)

        try:
            status = super().move(position, wait, **kwargs)
            return status
        except UnknownStatusFailure:
            status = DeviceStatus(self)
            status.set_finished()
            # return status
            raise


class EpicsMotorEC(EpicsMotorMR):
    """ Detailed ECMC EPICS motor class

    Special motor class to provide additional functionality  for ECMC based motors.
    It exposes additional diagnostic fields and includes basic error management.
    """
    USER_ACCESS = ['reset']
    enable_readback = Component(EpicsSignalRO, "-EnaAct", auto_monitor=True, kind=Kind.normal)
    enable = Component(
        EpicsSignal, "-EnaCmd-RB", write_pv="-EnaCmd", auto_monitor=True, kind=Kind.normal)
    homed = Component(EpicsSignalRO, "-Homed", auto_monitor=True, kind=Kind.normal)
    velocity_readback = Component(EpicsSignalRO, "-VelAct", auto_monitor=True, kind=Kind.normal)
    position_readback = Component(EpicsSignalRO, "-PosAct", auto_monitor=True, kind=Kind.normal)
    position_error = Component(EpicsSignalRO, "-PosErr", auto_monitor=True, kind=Kind.normal)
    # high_interlock = Component(EpicsSignalRO, "-SumIlockFwd", auto_monitor=True, kind=Kind.normal)
    # low_interlock = Component(EpicsSignalRO, "-SumIlockBwd", auto_monitor=True, kind=Kind.normal)

    # ecmc_status = Component(EpicsSignalRO, "-Status", auto_monitor=True, kind=Kind.normal)
    error = Component(EpicsSignalRO, "-ErrId", auto_monitor=True, kind=Kind.normal)
    error_msg = Component(EpicsSignalRO, "-MsgTxt", auto_monitor=True, kind=Kind.normal)
    error_reset = Component(EpicsSignal, "-ErrRst", put_complete=True, kind=Kind.omitted)

    def move(self, position, wait=True, **kwargs) -> MoveStatus:
        """ Extended move function with a few sanity checks

        Note that the default EpicsMotor only supports the 'GO' movement mode.
        """
        # Check ECMC error status before move
        error = self.error.get()
        if error:
            raise RuntimeError(f"Motor is in error state with message: '{self.error_msg.get()}'")

        return super().move(position, wait, **kwargs)

    def reset(self):
        """ Resets an ECMC axis

        Recovers an ECMC axis from a previous error. Note that this does not
        solve the cause of the error, that you'll have to do yourself.

        Common error causes:
        -------------------------
        - MAX_POSITION_LAG_EXCEEDED : The PID tuning is wrong.
        - MAX_VELOCITY_EXCEEDED : PID is wrong or the motor is sticking-slipping
        - BOTH_LIMITS_ACTIVE : The motors are probably not connected
        """
        # Reset the error
        self.error_reset.set(1, settle_time=0.1).wait()
        # Check if it disappeared
        if self.error.get():
            raise RuntimeError(f"Failed to reset axis, still in error: '{self.error_msg.get()}'")
