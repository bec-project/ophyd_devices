import threading
from time import sleep
from unittest.mock import ANY, MagicMock, patch

import ophyd
import pytest
from ophyd.device import Component as Cpt
from ophyd.signal import EpicsSignal, EpicsSignalRO, Kind, Signal
from ophyd.sim import FakeEpicsSignal, FakeEpicsSignalRO

from ophyd_devices.devices.simple_positioner import PSISimplePositioner
from ophyd_devices.interfaces.base_classes.psi_positioner_base import (
    PSIPositionerBase,
    PSISimplePositionerBase,
    RequiredSignalNotSpecified,
)
from ophyd_devices.tests.utils import MockPV, patch_dual_pvs


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
@patch("ophyd_devices.interfaces.base_classes.psi_positioner_base.PositionerBase.move")
@patch("ophyd_devices.interfaces.base_classes.psi_positioner_base.MoveStatus")
def test_instant_completion_within_deadband(
    mock_movestatus,
    mock_super_move,
    mock_psi_positioner: PSISimplePositioner,
    start,
    end,
    in_deadband_expected,
):
    mock_psi_positioner._position = start
    mock_psi_positioner.move(end)

    if in_deadband_expected:
        mock_movestatus.assert_called_with(ANY, ANY, done=True, success=True)
    else:
        mock_movestatus.assert_not_called()
        mock_super_move.assert_called_once()


def test_status_completed_when_req_done_sub_runs(mock_psi_positioner: PSISimplePositioner):
    mock_psi_positioner.motor_done_move._read_pv.mock_data = 0
    mock_psi_positioner._position = 0
    st = mock_psi_positioner.move(1, wait=False)
    assert not st.done
    mock_psi_positioner._run_subs(sub_type=mock_psi_positioner._SUB_REQ_DONE)
    assert st.done


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


def test_put_complete_positioner():
    class PsiTestPosPutComplete(PSISimplePositionerBase):
        user_setpoint: EpicsSignal = Cpt(EpicsSignal, ".VAL", auto_monitor=True)
        user_readback = Cpt(EpicsSignalRO, ".RBV", kind="hinted", auto_monitor=True)

    with patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        dev = PsiTestPosPutComplete("prefix:", name="test", use_put_completion=True, deadband=0.001)
        patch_dual_pvs(dev)
        dev.wait_for_connection()
        dev.user_setpoint._read_pv._put_complete_event = threading.Event()
        dev._set_position(0)

    st = dev.move(6, wait=False)
    assert dev.user_setpoint.get() == 6
    assert not st.done
    dev.user_setpoint._read_pv._put_complete_event.set()
    sleep(1)
    assert st.done
