"""This module tests the EpicsMotor and EpicsMotorEC classes for custom
PSI motor integration from the ophyd_devices.devices.psi_motor module."""

from __future__ import annotations

import threading
from unittest import mock

import ophyd
import pytest

from ophyd_devices.devices.psi_motor import EpicsMotor, EpicsMotorEC, SpmgStates
from ophyd_devices.tests.utils import MockPV, patch_dual_pvs


@pytest.fixture(scope="function")
def mock_epics_motor():
    """Fixture to create a mock EpicsMotor instance."""
    name = "test_motor"
    prefix = "SIM:MOTOR"
    with mock.patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        motor = EpicsMotor(name=name, prefix=prefix)
        motor.wait_for_connection()
        patch_dual_pvs(motor)
        yield motor


@pytest.fixture(scope="function")
def mock_epics_motor_ec():
    """Fixture to create a mock EpicsMotorEC instance."""
    name = "test_motor_ec"
    prefix = "SIM:MOTOR:EC"
    with mock.patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        motor_ec = EpicsMotorEC(name=name, prefix=prefix)
        motor_ec.wait_for_connection()
        patch_dual_pvs(motor_ec)
        yield motor_ec


def test_epics_motor_limits_raise(mock_epics_motor):
    """Test the move method of EpicsMotor."""
    motor = mock_epics_motor
    motor.user_setpoint._metadata["lower_ctrl_limit"] = -10
    motor.user_setpoint._metadata["upper_ctrl_limit"] = 10
    motor.low_limit_travel.put(-10)
    motor.high_limit_travel.put(10)
    with pytest.raises(ophyd.utils.LimitError):
        motor.move(-15)


def test_epics_motor_move(mock_epics_motor):
    """Test the move method of EpicsMotor."""
    motor = mock_epics_motor
    assert motor.user_readback.get() == 0
    assert motor.user_setpoint.get() == 0
    motor.user_setpoint._metadata["lower_ctrl_limit"] = -10
    motor.user_setpoint._metadata["upper_ctrl_limit"] = 10
    motor.motor_mode.put(SpmgStates.GO)
    # Now this should raise... in theory...
    motor.user_readback._read_pv.set_severity(ophyd.utils.epics_pvs.AlarmSeverity.NO_ALARM)
    motor.user_readback._metadata["severity"] = ophyd.utils.epics_pvs.AlarmSeverity.NO_ALARM
    motor.user_readback._read_pv.set_alarm_status(ophyd.utils.epics_pvs.AlarmStatus.NO_ALARM)
    motor.user_readback._metadata["status"] = ophyd.utils.epics_pvs.AlarmStatus.NO_ALARM
    # Set alarm of motor to
    status = motor.move(5)
    assert status.done is False
    assert motor.user_readback.get() == 0
    assert motor.user_setpoint.get() == 5
    motor.motor_done_move._read_pv.mock_data = 0
    for ii in range(1, 6):
        motor.user_readback._read_pv.mock_data = ii
        if ii == 5:
            motor.motor_done_move._read_pv.mock_data = 1
        else:
            motor.motor_done_move._read_pv.mock_data = 0

    status.wait(timeout=5)
    assert status.done is True
    assert motor.user_readback.get() == 5
    assert motor.user_setpoint.get() == 5

    # Now this should raise...
    motor.user_readback._read_pv.set_severity(ophyd.utils.epics_pvs.AlarmSeverity.MAJOR)
    motor.user_readback._metadata["severity"] = ophyd.utils.epics_pvs.AlarmSeverity.MAJOR
    motor.user_readback._read_pv.set_alarm_status(ophyd.utils.epics_pvs.AlarmStatus.READ)
    motor.user_readback._metadata["status"] = ophyd.utils.epics_pvs.AlarmStatus.READ
    status = motor.move(10)
    motor.motor_done_move._read_pv.mock_data = 0
    assert status.done is False
    assert motor.user_readback.get() == 5
    assert motor.user_setpoint.get() == 10
    motor.user_readback._read_pv.mock_data = 7
    motor.motor_done_move._read_pv.mock_data = 0
    assert status.done is False
    motor.user_readback._read_pv.mock_data = 10
    motor.motor_done_move._read_pv.mock_data = 1
    with pytest.raises(RuntimeError):
        status.wait(timeout=5)
        assert status.done is True
        assert isinstance(status.exception(), RuntimeError)


def test_move_epics_motor_ec(mock_epics_motor_ec):
    """Test the move method of EpicsMotorEC."""
    motor_ec = mock_epics_motor_ec
    motor_ec.user_setpoint._metadata["lower_ctrl_limit"] = -10
    motor_ec.user_setpoint._metadata["upper_ctrl_limit"] = 10
    motor_ec.user_readback._read_pv.set_severity(ophyd.utils.epics_pvs.AlarmSeverity.NO_ALARM)
    motor_ec.user_readback._metadata["severity"] = ophyd.utils.epics_pvs.AlarmSeverity.NO_ALARM
    motor_ec.user_readback._read_pv.set_alarm_status(ophyd.utils.epics_pvs.AlarmStatus.NO_ALARM)
    motor_ec.user_readback._metadata["status"] = ophyd.utils.epics_pvs.AlarmStatus.NO_ALARM

    assert motor_ec.user_readback.get() == 0
    assert motor_ec.user_setpoint.get() == 0

    motor_ec.error._read_pv.mock_data = 0
    with mock.patch.object(motor_ec.log, "warning") as mock_log_warning:
        # Should not log any warning
        status = motor_ec.move(5)
        motor_ec.motor_done_move._read_pv.mock_data = 0
        assert mock_log_warning.call_count == 0
        motor_ec.user_readback._read_pv.mock_data = 5
        motor_ec.motor_done_move._read_pv.mock_data = 1
        status.wait(timeout=5)
        assert status.done is True

        # If error exists, this should raise a warning
        motor_ec.error._read_pv.mock_data = 1
        status = motor_ec.move(8)
        motor_ec.motor_done_move._read_pv.mock_data = 0
        assert status.done is False
        assert mock_log_warning.call_count == 1
        motor_ec.user_readback._read_pv.mock_data = 8
        motor_ec.motor_done_move._read_pv.mock_data = 1
        with pytest.raises(RuntimeError):
            status.wait(timeout=5)
            assert status.done is True
            assert isinstance(status.exception(), RuntimeError)

        motor_ec.error._read_pv.mock_data = 0
        # Note: Position has to be > current position from 8 to 9...
        motor_ec.high_interlock._read_pv.mock_data = 1
        status = motor_ec.move(9)
        motor_ec.motor_done_move._read_pv.mock_data = 0
        assert status.done is False
        assert mock_log_warning.call_count == 2
        motor_ec.user_readback._read_pv.mock_data = 2
        motor_ec.motor_done_move._read_pv.mock_data = 1
        motor_ec.high_interlock._read_pv.mock_data = 0
        status.wait(timeout=5)
        assert status.done is True

        # Attempting to move below active LLS should raise a warning
        motor_ec.low_interlock._read_pv.mock_data = 1
        status = motor_ec.move(-2)
        motor_ec.motor_done_move._read_pv.mock_data = 0
        assert status.done is False
        assert mock_log_warning.call_count == 3
        motor_ec.user_readback._read_pv.mock_data = -2
        motor_ec.motor_done_move._read_pv.mock_data = 1
        status.wait(timeout=5)
        assert status.done is True
        motor_ec.low_interlock._read_pv.mock_data = 0


def test_epics_motor_high_limit_switch_raises(mock_epics_motor):
    """Test that moving beyond high limit switch raises an error."""
    motor = mock_epics_motor
    motor.user_setpoint._metadata["lower_ctrl_limit"] = -10
    motor.user_setpoint._metadata["upper_ctrl_limit"] = 10
    motor.high_limit_switch._read_pv.mock_data = 1  # Simulate high limit switch active
    with pytest.raises(ophyd.utils.LimitError):
        motor.move(15)
