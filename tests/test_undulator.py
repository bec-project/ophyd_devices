import threading
from unittest import mock

import ophyd
import pytest

from ophyd_devices.devices.undulator import UndulatorGap
from ophyd_devices.tests.utils import MockPV, patch_dual_pvs


@pytest.fixture(scope="function")
def mock_undulator():
    name = "undulator"
    prefix = "TEST:UNDULATOR"
    with mock.patch.object(ophyd, "cl") as mock_cl:
        mock_cl.get_pv = MockPV
        mock_cl.thread_class = threading.Thread
        dev = UndulatorGap(name=name, prefix=prefix)
        patch_dual_pvs(dev)
        yield dev


@pytest.mark.parametrize(
    ["start", "end", "in_deadband_expected"],
    [
        (1.0, 1.0, True),
        (0, 1.0, False),
        (-0.004, 0.004, False),
        (-0.0027, -0.0023, True),
        (1, 1.0009, False),
        (1, 1.0007, True),
    ],
)
@mock.patch("ophyd_devices.devices.undulator.PVPositioner.move")
@mock.patch("ophyd_devices.devices.undulator.MoveStatus")
def test_instant_completion_within_deadband(
    mock_movestatus, mock_super_move, mock_undulator, start, end, in_deadband_expected
):
    mock_undulator.select_control._read_pv.mock_data = 1
    mock_undulator._position = start
    mock_undulator.move(end)

    if in_deadband_expected:
        mock_movestatus.assert_called_with(mock.ANY, mock.ANY, done=True, success=True)
    else:
        mock_movestatus.assert_not_called()
        mock_super_move.assert_called_once()


def test_undulator_raises_when_disabled(mock_undulator):
    mock_undulator.select_control._read_pv.mock_data = 0
    with pytest.raises(PermissionError) as e:
        mock_undulator.move(5)
    assert e.match("Undulator is operator controlled!")


def test_undulator_stop_call(mock_undulator):
    mock_undulator.select_control._read_pv.mock_data = 1
    mock_undulator.stop()
    mock_undulator.select_control._read_pv.mock_data = 0
    with pytest.raises(PermissionError) as e:
        mock_undulator.stop()
