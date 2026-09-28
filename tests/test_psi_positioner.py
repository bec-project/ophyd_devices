import threading
from unittest.mock import ANY, patch

import ophyd
import pytest
from ophyd.device import Component as Cpt
from ophyd.signal import EpicsSignal, Kind, Signal
from ophyd.sim import FakeEpicsSignal, FakeEpicsSignalRO
from ophyd.utils import StatusTimeoutError

from ophyd_devices.devices.simple_positioner import PSISimplePositioner
from ophyd_devices.interfaces.base_classes.psi_positioner_base import (
    PSIPositionerBase,
    PSISimplePositionerBase,
    RequiredSignalNotSpecified,
)
from ophyd_devices.tests.utils import MockPV, patch_dual_pvs
from ophyd_devices.utils.psi_device_base_utils import StatusTimeoutErrorWithErrorInfo


def test_cannot_isntantiate_without_required_signals():
    class PSITestPositionerWOSignal(PSISimplePositionerBase): ...

    class PSITestPositionerWithSignal(PSISimplePositionerBase):
        user_setpoint: EpicsSignal = Cpt(FakeEpicsSignal, ".VAL", limits=True, auto_monitor=True)
        user_readback = Cpt(FakeEpicsSignalRO, ".RBV", kind="hinted", auto_monitor=True)
        motor_done_move = Cpt(FakeEpicsSignalRO, ".DMOV", auto_monitor=True)

    with pytest.raises(RequiredSignalNotSpecified) as e:
        PSITestPositionerWOSignal("", name="")
        assert e.match("user_setpoint")
        assert e.match("user_readback")

    dev = PSITestPositionerWithSignal("", name="")
    assert dev.user_setpoint.get() == 0


def test_override_suffixes():
    pos = PSISimplePositioner(
        name="name",
        prefix="prefix:",
        override_suffixes={"user_readback": "RDB", "motor_done_move": "DONE"},
    )
    assert pos.user_readback._read_pvname == "prefix:RDB"
    assert pos.motor_done_move._read_pvname == "prefix:DONE"


@patch("ophyd.ophydobj.LoggerAdapter")
def test_override_suffixes_warns_on_nonimplemented(ophyd_logger):
    _ = PSISimplePositioner(name="name", prefix="prefix:", override_suffixes={"motor_stop": "STOP"})
    ophyd_logger().warning.assert_called_with(
        "<class 'ophyd_devices.devices.simple_positioner.PSISimplePositioner'> does not implement overridden signal motor_stop"
    )


@pytest.fixture()
def mock_psi_positioner():
    name = "positioner"
    prefix = "SIM:MOTOR"
    with patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        dev = PSISimplePositioner(name=name, prefix=prefix, deadband=0.0013)
        dev.wait_for_connection()
        patch_dual_pvs(dev)
        yield dev


@pytest.mark.parametrize(
    ["start", "end", "in_deadband_expected"],
    [
        (1.0, 1.0, True),
        (0, 1.0, False),
        (-0.004, 0.004, False),
        (-0.0027, -0.0023, True),
        (1, 1.0014, False),
        (1, 1.0012, True),
    ],
)
@patch("ophyd_devices.interfaces.base_classes.psi_positioner_base.MoveStatusWithTolerance")
@patch.object(PSISimplePositionerBase, "_setup_move")
@patch("ophyd_devices.interfaces.base_classes.psi_positioner_base.MoveStatus")
def test_instant_completion_within_deadband(
    mock_movestatus,
    mock_setup_move,
    mock_move_status_with_tolerance,
    mock_psi_positioner: PSISimplePositioner,
    start,
    end,
    in_deadband_expected,
):
    mock_psi_positioner._position = start
    mock_psi_positioner.move(end, wait=False)

    if in_deadband_expected:
        mock_movestatus.assert_called_with(ANY, ANY, done=True, success=True)
        mock_move_status_with_tolerance.assert_not_called()
        mock_setup_move.assert_not_called()
    else:
        mock_movestatus.assert_not_called()
        mock_move_status_with_tolerance.assert_called_once()
        mock_setup_move.assert_called_once_with(end)


def test_status_completed_when_req_done_sub_runs(mock_psi_positioner: PSISimplePositioner):
    mock_psi_positioner.motor_done_move._read_pv.mock_data = 0
    mock_psi_positioner._position = 0
    st = mock_psi_positioner.move(1, wait=False)
    assert not st.done
    mock_psi_positioner._run_subs(sub_type=mock_psi_positioner._SUB_REQ_DONE)
    assert st.done


def test_mdm_used_for_moving_if_available(mock_psi_positioner):
    mock_psi_positioner.wait_for_connection()
    mock_psi_positioner.motor_done_move._read_pv.mock_data = 0
    assert mock_psi_positioner.moving
    mock_psi_positioner.motor_done_move._read_pv.mock_data = 1
    assert not mock_psi_positioner.moving


def test_stop_puts_to_readback(mock_psi_positioner):
    mock_psi_positioner.user_readback._read_pv.mock_data = 12.34
    mock_psi_positioner.stop()
    assert mock_psi_positioner.user_setpoint.get() == 12.34


def test_psi_positioner_soft_limits():
    class PsiTestPosWSoftLimits(PSIPositionerBase):
        user_setpoint: EpicsSignal = Cpt(FakeEpicsSignal, ".VAL", limits=True, auto_monitor=True)
        user_readback = Cpt(FakeEpicsSignalRO, ".RBV", kind="hinted", auto_monitor=True)
        motor_done_move = Cpt(FakeEpicsSignalRO, ".DMOV", auto_monitor=True)

        low_limit_travel = Cpt(Signal, value=0, kind=Kind.omitted)
        high_limit_travel = Cpt(Signal, value=0, kind=Kind.omitted)

    device = PsiTestPosWSoftLimits(name="name", prefix="", limits=[-1.5, 1.5])
    assert isinstance(device.low_limit_travel, Signal)
    assert isinstance(device.high_limit_travel, Signal)
    assert device.low_limit_travel.get() == -1.5
    assert device.high_limit_travel.get() == 1.5


class ReadbackPositioner(PSISimplePositionerBase):
    user_readback = Cpt(FakeEpicsSignalRO, "R")
    user_setpoint = Cpt(FakeEpicsSignal, "S")


class ReadbackPositionerWithTolerance(PSISimplePositionerBase):
    user_readback = Cpt(FakeEpicsSignalRO, "R")
    user_setpoint = Cpt(FakeEpicsSignal, "S")
    tolerance = Cpt(Signal, value=0.001)


class DoneSignalPositionerWithTolerance(PSISimplePositionerBase):
    user_readback = Cpt(FakeEpicsSignalRO, "R")
    user_setpoint = Cpt(FakeEpicsSignal, "S")
    motor_done_move = Cpt(FakeEpicsSignalRO, "D")
    tolerance = Cpt(Signal, value=0.001)


@pytest.fixture()
def mock_readback_positioner():
    name = "positioner"
    prefix = "SIM:MOTOR"
    with patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        dev = ReadbackPositioner(name=name, prefix=prefix, deadband=0.0013)
        patch_dual_pvs(dev)
        dev.wait_for_connection()
        dev._set_position(0)
        yield dev


@pytest.fixture()
def mock_done_signal_positioner_with_tolerance():
    name = "positioner"
    prefix = "SIM:MOTOR"
    with patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        dev = DoneSignalPositionerWithTolerance(name=name, prefix=prefix, deadband=0.001)
        patch_dual_pvs(dev)
        dev.wait_for_connection()
        dev._set_position(0)
        yield dev


@pytest.mark.parametrize(
    "setpoint,move_positions,completes",
    [
        (5, [2, 4, 5], True),
        (-5, [-2, -4, -4.9986], False),
        (-5, [-2, -4, -4.9988], True),
        (2, [2], True),
        (2, [0.2, 0.3, 0.4, 0.5], False),
    ],
)
def test_done_move_based_on_readback(mock_readback_positioner, setpoint, move_positions, completes):
    mock_readback_positioner.wait_for_connection()
    st = mock_readback_positioner.move(setpoint, wait=False)
    final_pos = move_positions.pop()
    assert mock_readback_positioner.user_setpoint.get() == setpoint
    assert not st.done

    for pos in move_positions:
        mock_readback_positioner.user_readback.sim_put(pos)
        assert not st.done

    mock_readback_positioner.user_readback.sim_put(final_pos)
    assert st.done == completes


def test_tolerance_success_with_done_signal_positioner(mock_done_signal_positioner_with_tolerance):
    st = mock_done_signal_positioner_with_tolerance.move(5, wait=False)

    mock_done_signal_positioner_with_tolerance.motor_done_move.sim_put(0)
    mock_done_signal_positioner_with_tolerance.user_readback.sim_put(4.9995)
    mock_done_signal_positioner_with_tolerance.motor_done_move.sim_put(1)

    assert st.done
    assert st.success
    assert st.exception() is None


def test_tolerance_failure_sets_move_status_exception(mock_done_signal_positioner_with_tolerance):
    st = mock_done_signal_positioner_with_tolerance.move(5, wait=False)

    mock_done_signal_positioner_with_tolerance.motor_done_move.sim_put(0)
    mock_done_signal_positioner_with_tolerance.user_readback.sim_put(4.995)
    mock_done_signal_positioner_with_tolerance.motor_done_move.sim_put(1)

    assert st.done
    assert not st.success
    with pytest.raises(RuntimeError, match="outside of tolerance"):
        st.wait(timeout=1)


def test_tolerance_failure_after_motion_does_not_stop_or_rewrite_setpoint(
    mock_done_signal_positioner_with_tolerance,
):
    dev = mock_done_signal_positioner_with_tolerance
    st = dev.move(5, wait=False)
    callbacks_finished = threading.Event()
    st.add_callback(lambda _: callbacks_finished.set())

    # The move itself already wrote the setpoint. Only watch for extra writes
    # caused by handling a tolerance failure after motion has completed.
    with (
        patch.object(dev, "stop", wraps=dev.stop) as stop,
        patch.object(dev.user_setpoint, "put", wraps=dev.user_setpoint.put) as put,
    ):
        dev.motor_done_move.sim_put(0)
        dev.user_readback.sim_put(4.995)
        dev.motor_done_move.sim_put(1)
        assert callbacks_finished.wait(timeout=1)
        stop.assert_not_called()
        put.assert_not_called()

    assert dev.user_setpoint.get() == 5
    with pytest.raises(RuntimeError, match="outside of tolerance"):
        st.wait(timeout=1)


def test_unrelated_move_failure_still_stops_positioner(mock_done_signal_positioner_with_tolerance):
    dev = mock_done_signal_positioner_with_tolerance
    st = dev.move(5, wait=False)
    callbacks_finished = threading.Event()
    st.add_callback(lambda _: callbacks_finished.set())

    with patch.object(dev, "stop", wraps=dev.stop) as stop:
        st.set_exception(RuntimeError("move aborted"))
        assert callbacks_finished.wait(timeout=1)
        stop.assert_called_once()


def test_tolerance_checks_requested_target_even_if_setpoint_changes(
    mock_done_signal_positioner_with_tolerance,
):
    dev = mock_done_signal_positioner_with_tolerance
    st = dev.move(5, wait=False)

    dev.motor_done_move.sim_put(0)
    dev.user_setpoint.put(4)
    dev.user_readback.sim_put(4)
    dev.motor_done_move.sim_put(1)

    assert st.target == 5
    with pytest.raises(RuntimeError, match="outside of tolerance"):
        st.wait(timeout=1)


@pytest.mark.parametrize("signal_name", ["tolerance", "user_readback"])
def test_completion_read_error_fails_without_stopping_or_rewriting_setpoint(
    mock_done_signal_positioner_with_tolerance, signal_name
):
    dev = mock_done_signal_positioner_with_tolerance
    st = dev.move(5, wait=False)
    dev.motor_done_move.sim_put(0)
    callbacks_finished = threading.Event()
    st.add_callback(lambda _: callbacks_finished.set())
    read_error = RuntimeError(f"{signal_name} read failed")

    with (
        patch.object(getattr(dev, signal_name), "get", side_effect=read_error),
        patch.object(dev, "stop", wraps=dev.stop) as stop,
        patch.object(dev.user_setpoint, "put", wraps=dev.user_setpoint.put) as put,
    ):
        dev.motor_done_move.sim_put(1)
        assert callbacks_finished.wait(timeout=1)
        with pytest.raises(RuntimeError) as raised:
            st.wait(timeout=1)
        assert raised.value is read_error
        stop.assert_not_called()
        put.assert_not_called()


def test_completion_read_status_timeout_is_wrapped_and_finishes(
    mock_done_signal_positioner_with_tolerance,
):
    dev = mock_done_signal_positioner_with_tolerance
    st = dev.move(5, wait=False)
    dev.motor_done_move.sim_put(0)
    callbacks_finished = threading.Event()
    st.add_callback(lambda _: callbacks_finished.set())
    read_error = StatusTimeoutError("final read timed out")

    with patch.object(dev.tolerance, "get", side_effect=read_error):
        dev.motor_done_move.sim_put(1)
        assert callbacks_finished.wait(timeout=1)

    with pytest.raises(RuntimeError) as raised:
        st.wait(timeout=1)
    assert raised.value.__cause__ is read_error


def test_late_completion_read_error_preserves_move_timeout_and_stop(
    mock_done_signal_positioner_with_tolerance,
):
    dev = mock_done_signal_positioner_with_tolerance
    st = dev.move(5, wait=False, timeout=0.5)
    dev.motor_done_move.sim_put(0)
    entered_read = threading.Event()
    release_read = threading.Event()
    callbacks_finished = threading.Event()
    st.add_callback(lambda _: callbacks_finished.set())
    read_error = RuntimeError("late tolerance read failure")

    def blocked_read():
        entered_read.set()
        assert release_read.wait(timeout=2)
        raise read_error

    with (
        patch.object(dev.tolerance, "get", side_effect=blocked_read),
        patch.object(dev, "stop", wraps=dev.stop) as stop,
    ):
        completion_thread = threading.Thread(target=dev.motor_done_move.sim_put, args=(1,))
        completion_thread.start()
        try:
            assert entered_read.wait(timeout=1)
            assert not st.done
            assert callbacks_finished.wait(timeout=2)
            with pytest.raises(StatusTimeoutErrorWithErrorInfo) as timed_out:
                st.wait(timeout=1)
            stop.assert_called_once()
        finally:
            release_read.set()
            completion_thread.join(timeout=1)

        assert not completion_thread.is_alive()
        with pytest.raises(StatusTimeoutErrorWithErrorInfo) as after_read:
            st.wait(timeout=1)
        assert after_read.value is timed_out.value
        stop.assert_called_once()


def test_move_timeout_remains_structured_after_stop_cancels_done_status(
    mock_done_signal_positioner_with_tolerance,
):
    dev = mock_done_signal_positioner_with_tolerance
    st = dev.move(5, wait=False, timeout=0.2)
    dev.motor_done_move.sim_put(0)
    callbacks_finished = threading.Event()
    st.add_callback(lambda _: callbacks_finished.set())

    with (
        patch.object(
            dev.tolerance, "get", side_effect=AssertionError("unexpected final read")
        ) as get,
        patch.object(dev, "stop", wraps=dev.stop) as stop,
        patch.object(dev, "_done_moving", wraps=dev._done_moving) as done_moving,
    ):
        assert callbacks_finished.wait(timeout=2)
        with pytest.raises(StatusTimeoutErrorWithErrorInfo):
            st.wait(timeout=1)
        stop.assert_called_once()
        done_moving.assert_any_call(success=False)
        get.assert_not_called()


def test_infinite_tolerance_completion_does_not_read_final_position(mock_psi_positioner):
    dev = mock_psi_positioner
    assert dev.tolerance.get() == float("inf")
    st = dev.move(5, wait=False)
    dev.motor_done_move._read_pv.mock_data = 0

    with patch.object(dev.user_readback, "get", side_effect=RuntimeError("unexpected read")) as get:
        dev.motor_done_move._read_pv.mock_data = 1
        st.wait(timeout=1)
        get.assert_not_called()

    assert st.success


def test_move_rejects_tolerance_tighter_than_deadband_before_setpoint_write(
    mock_done_signal_positioner_with_tolerance,
):
    dev = mock_done_signal_positioner_with_tolerance
    dev.tolerance.put(0.0005)

    with patch.object(dev.user_setpoint, "put", wraps=dev.user_setpoint.put) as put:
        with pytest.raises(ValueError, match="tolerance"):
            dev.move(5, wait=False)
        put.assert_not_called()


def test_equal_deadband_and_tolerance_allow_instant_success(
    mock_done_signal_positioner_with_tolerance,
):
    dev = mock_done_signal_positioner_with_tolerance
    assert dev.tolerance.get() == dev._deadband

    with patch.object(dev.user_setpoint, "put", wraps=dev.user_setpoint.put) as put:
        st = dev.move(0.0005, wait=False)
        put.assert_not_called()

    assert st.done
    assert st.success
