import threading
from unittest.mock import ANY, MagicMock, patch

import ophyd
import pytest
from ophyd.device import Component as Cpt
from ophyd.signal import EpicsSignal
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


@pytest.fixture(scope="function")
def mock_psi_positioner() -> PSISimplePositioner:
    name = "positioner"
    prefix = "SIM:MOTOR"
    with patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        dev = PSISimplePositioner(name=name, prefix=prefix, deadband=0.0013)
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
